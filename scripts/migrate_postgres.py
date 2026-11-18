"""One-time, verified SQLite → PostgreSQL transfer. Never loads runtime settings."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Connection, MetaData, Table, Text, create_engine, inspect, select, text
from sqlalchemy.engine import make_url

from backend.app.db import models  # noqa: F401
from backend.app.db.base import Base

ROOT = Path(__file__).resolve().parent.parent
LOCAL_POSTGRES_URL = "postgresql+psycopg://margin:margin_local_dev@127.0.0.1:5437/margin"


class TransferError(Exception):
    """A safe, actionable error containing no credentials or row values."""


def migration_config(connection: Connection | None = None) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


@contextmanager
def sqlite_snapshot(path: Path) -> Iterator[Connection]:
    path = path.resolve(strict=True)
    if path.suffix not in {".db", ".sqlite", ".sqlite3"} or any(
        part == ".env" or part.startswith(".env.") for part in path.parts
    ):
        raise TransferError("Source must be an existing SQLite database file, never a dotenv file.")
    # SQLite URI mode=ro forbids source writes; explicit BEGIN fixes the snapshot
    # even on Python sqlite3's legacy transaction mode. No WAL/PRAGMA mutations.
    engine = create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true", hide_parameters=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA query_only=ON")
            connection.exec_driver_sql("BEGIN")
            yield connection
            connection.rollback()
    finally:
        engine.dispose()


def checked_metadata(connection: Connection) -> MetaData:
    expected = set(Base.metadata.tables) | {"alembic_version"}
    if set(inspect(connection).get_table_names()) != expected:
        raise TransferError(
            "Database table list differs from the application schema; nothing was transferred."
        )
    if set(MigrationContext.configure(connection).get_current_heads()) != set(
        ScriptDirectory.from_config(migration_config()).get_heads()
    ):
        raise TransferError("Database is not at the current Alembic revision; upgrade it before transfer.")
    if compare_metadata(MigrationContext.configure(connection), Base.metadata):
        raise TransferError(
            "Database structure differs from the ORM/Alembic schema; investigate before transfer."
        )
    metadata = MetaData()
    metadata.reflect(connection)
    # Distinguish SQL NULL from the JSON document null during the transfer.
    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSON):
                column.type = JSON(none_as_null=True)
    return metadata


def records(connection: Connection, table: Table) -> list[dict[str, Any]]:
    # Read raw JSON text, then decode ourselves. SQLAlchemy normally collapses
    # SQL NULL and JSON null to the same Python None, losing that distinction.
    columns = [
        column.cast(Text).label(column.name) if isinstance(column.type, JSON) else column
        for column in table.columns
    ]
    return [dict(row) for row in connection.execute(select(*columns).order_by(*table.primary_key)).mappings()]


def comparable(rows: list[dict[str, Any]], table: Table) -> list[dict[str, Any]]:
    result = []
    for original in rows:
        row = original.copy()
        for column in table.columns:
            if column.name == "embedding":
                raw = row[column.name]
                decoded = json.loads(raw) if isinstance(raw, str) else raw
                row[column.name] = None if decoded is None else np.asarray(decoded, dtype=np.float32).tolist()
            elif isinstance(column.type, JSON):
                raw = row[column.name]
                row[column.name] = ("sql_null",) if raw is None else ("json", json.loads(raw))
        result.append(row)
    return result


def insert_values(rows: list[dict[str, Any]], table: Table) -> list[dict[str, Any]]:
    result = []
    for original in rows:
        row = original.copy()
        for column in table.columns:
            if isinstance(column.type, Vector):
                raw = row[column.name]
                row[column.name] = json.loads(raw) if isinstance(raw, str) else raw
            elif isinstance(column.type, JSON):
                raw = row[column.name]
                if raw is not None:
                    decoded = json.loads(raw)
                    row[column.name] = JSON.NULL if decoded is None else decoded
        result.append(row)
    return result


def transfer(source_path: Path, target_url: str, *, verify_only: bool = False) -> dict[str, int]:
    url = make_url(target_url)
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise TransferError("Target must be PostgreSQL using the psycopg driver.")
    # Never put a URL through ConfigParser (percent signs in passwords are valid).
    target = create_engine(url.set(drivername="postgresql+psycopg"), hide_parameters=True)
    try:
        with sqlite_snapshot(source_path) as source:
            source_metadata = checked_metadata(source)
            if source.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise TransferError("Source has foreign-key violations; nothing was transferred.")
            tables = [t for t in source_metadata.sorted_tables if t.name != "alembic_version"]
            snapshot = {table.name: records(source, table) for table in tables}
            with target.begin() as destination:
                # Serialize concurrent imports and protect target rows during verification.
                destination.execute(text("SELECT pg_advisory_xact_lock(726431900)"))
                if not verify_only:
                    existing = set(inspect(destination).get_table_names())
                    if existing - (set(Base.metadata.tables) | {"alembic_version"}):
                        raise TransferError(
                            "Target contains unrelated tables; choose a dedicated empty database."
                        )
                    command.upgrade(migration_config(destination), "head")
                target_metadata = checked_metadata(destination)
                for table in tables:
                    # Identifiers come only from our fixed schema, not user input.
                    destination.execute(text(f'LOCK TABLE "{table.name}" IN ACCESS EXCLUSIVE MODE'))
                if not verify_only:
                    for table in tables:
                        target_table = target_metadata.tables[table.name]
                        if destination.execute(select(target_table).limit(1)).first() is not None:
                            raise TransferError(
                                "Target contains application data; refusing to overwrite or merge it."
                            )
                    for table in tables:
                        target_table = target_metadata.tables[table.name]
                        rows = insert_values(snapshot[table.name], target_table)
                        for offset in range(0, len(rows), 500):
                            destination.execute(target_table.insert(), rows[offset : offset + 500])
                for table in tables:
                    actual = records(destination, target_metadata.tables[table.name])
                    if comparable(snapshot[table.name], table) != comparable(actual, table):
                        raise TransferError(
                            f"Full content verification failed for {table.name}; transfer rolled back."
                        )
                # PostgreSQL's non-deferrable FK/unique constraints were enforced on
                # every insert; schema + content verification occurs before commit.
            return {name: len(rows) for name, rows in snapshot.items()}
    finally:
        target.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "margin.db")
    parser.add_argument("--target-url", default=LOCAL_POSTGRES_URL)
    parser.add_argument(
        "--verify-only", action="store_true", help="Compare current source snapshot to target; no writes"
    )
    args = parser.parse_args()
    try:
        counts = transfer(args.source, args.target_url, verify_only=args.verify_only)
    except TransferError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        # Driver exceptions can include passwords, SQL parameter values or book text.
        print(
            f"Transfer failed ({type(error).__name__}); target transaction rolled back. No row values or URL logged.",
            file=sys.stderr,
        )
        return 1
    for table, count in counts.items():
        print(f"{table}: {count} rows verified")
    print("All application rows, JSON values, IDs and timestamps match the SQLite snapshot.")
    print("SQLite was opened read-only and remains unchanged. Photo paths were preserved; keep data/uploads.")
    print("This is a snapshot, not ongoing synchronization. Stop API/worker writers before final cutover,")
    print("then verify again, manually update DATABASE_URL and restart both processes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
