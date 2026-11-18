"""Real PostgreSQL checks; opt in with POSTGRES_TESTS=1, no private settings."""

import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, Table, create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import Settings
from backend.app.core.runtime import Runtime
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.modules.readings.models import ReadingSession
from scripts.migrate_postgres import (
    LOCAL_POSTGRES_URL,
    TransferError,
    migration_config,
    sqlite_snapshot,
    transfer,
)


def test_snapshot_is_read_only_and_does_not_create_missing_database(tmp_path: Path) -> None:
    missing = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        with sqlite_snapshot(missing):
            pass
    assert not missing.exists()
    source = tmp_path / "source.db"
    engine = create_engine(f"sqlite:///{source}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sample (value TEXT)"))
    engine.dispose()
    original = source.read_bytes()
    with sqlite_snapshot(source) as connection:
        with pytest.raises(Exception, match="readonly"):
            connection.execute(text("INSERT INTO sample VALUES ('forbidden')"))
    assert source.read_bytes() == original


@pytest.fixture
def postgres_url() -> Iterator[str]:
    if os.environ.get("POSTGRES_TESTS") != "1":
        pytest.skip("Set POSTGRES_TESTS=1 to use a disposable database in the local PostgreSQL container")
    name = f"margin_test_{uuid4().hex}"
    admin = create_engine(LOCAL_POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield LOCAL_POSTGRES_URL.rsplit("/", 1)[0] + "/" + name
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def populated_sqlite(tmp_path: Path) -> Path:
    source = tmp_path / "source.db"
    engine = create_engine(f"sqlite:///{source}")
    with engine.begin() as connection:
        command.upgrade(migration_config(connection), "head")
        row_ids = {}
        for table in Base.metadata.sorted_tables:
            row = {}
            for column in table.columns:
                if column.name == 'embedding':
                    row[column.name] = [0.1] * 1024
                elif column.name == 'keywords':
                    row[column.name] = None
                elif column.foreign_keys:
                    row[column.name] = row_ids[next(iter(column.foreign_keys)).column.table.name]
                elif isinstance(column.type, JSON):
                    row[column.name] = {"text": "Příliš žluťoučký — Canada", "nested": [1, True, None]}
                elif isinstance(column.type, Boolean):
                    row[column.name] = True
                elif isinstance(column.type, Integer):
                    row[column.name] = 1
                elif isinstance(column.type, Float):
                    row[column.name] = 0.001234
                elif isinstance(column.type, DateTime):
                    row[column.name] = datetime(2026, 11, 11, 10, 11, 12, 123456)
                else:
                    row[column.name] = (f"{table.name}_{column.name}")[: getattr(column.type, "length", None)]
            row_ids[table.name] = row[next(iter(table.primary_key)).name]
            if table.name == "reading_sessions":
                row["translation"] = None
            if table.name == "chat_turns":
                row["answer"] = JSON.NULL
            connection.execute(table.insert().values(**row))
        # Explicit SQL NULL as distinct from JSON null.
        connection.execute(text("UPDATE reading_sessions SET translation = NULL"))
    engine.dispose()
    return source


def test_full_schema_data_json_and_duplicate_refusal(postgres_url: str, populated_sqlite: Path) -> None:
    original = populated_sqlite.read_bytes()
    counts = transfer(populated_sqlite, postgres_url)
    assert set(counts) == set(Base.metadata.tables)
    assert all(count == 1 for count in counts.values())
    assert transfer(populated_sqlite, postgres_url, verify_only=True) == counts
    with pytest.raises(TransferError, match="refusing to overwrite"):
        transfer(populated_sqlite, postgres_url)
    assert transfer(populated_sqlite, postgres_url, verify_only=True) == counts
    assert populated_sqlite.read_bytes() == original


def test_failed_transfer_rolls_back_schema_and_data(
    postgres_url: str, populated_sqlite: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import migrate_postgres

    original = migrate_postgres.comparable
    calls = 0

    def mismatching(rows: list[dict[str, Any]], table: Table) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return original(rows, table) if calls == 1 else []

    monkeypatch.setattr(migrate_postgres, "comparable", mismatching)
    with pytest.raises(TransferError, match="verification failed"):
        transfer(populated_sqlite, postgres_url)
    engine = create_engine(postgres_url)
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all()
            == []
        )
    engine.dispose()


def test_postgres_http_and_chat_claims(postgres_url: str, tmp_path: Path) -> None:
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        command.upgrade(migration_config(connection), "head")
    config = Settings.model_construct(data_dir=tmp_path, database_url=postgres_url)
    runtime = Runtime(config, sessionmaker(engine, expire_on_commit=False), "dummy-test-owner")
    app = create_app(runtime, background_jobs=False, serve_frontend=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 1234)) as client:
        assert client.post("/api/bootstrap").status_code == 200
        response = client.post("/api/books", json={"title": "PostgreSQL čtení", "author": "Test"})
        assert response.status_code == 201
        book = response.json()
        assert client.get("/api/books").json()[0]["title"] == "PostgreSQL čtení"
        with runtime.sessions() as db:
            db.add(
                ReadingSession(
                    book_id=book["id"],
                    image_path="dummy.jpg",
                    extraction={"left_text": "Some source text", "right_text": "More source text"},
                )
            )
            db.commit()
        thread_response = client.post(f"/api/books/{book['id']}/chats", json={"language": "cs"})
        assert thread_response.status_code == 201
        thread = thread_response.json()
        payload = {"request_id": str(uuid4()), "question": "Co se stalo?"}
        first = client.post(f"/api/chats/{thread['id']}/messages", json=payload)
        assert first.status_code == 202
        duplicate = client.post(f"/api/chats/{thread['id']}/messages", json=payload)
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == first.json()["id"]
        competing = client.post(
            f"/api/chats/{thread['id']}/messages", json={**payload, "request_id": str(uuid4())}
        )
        assert competing.status_code == 409
    engine.dispose()


async def test_real_postgres_hybrid_search_uses_vector_distance_and_fts(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.modules.books.models import Book
    from backend.app.modules.knowledge.repository import KnowledgeRepository
    from backend.app.modules.knowledge.processing import KnowledgeProcessor
    from backend.app.modules.knowledge.schemas import ExtractedKnowledge
    from backend.app.knowledge import extraction

    class Encoder:
        def encode(self, texts):
            return [[1.,0.] + [0.] * 1022 if any(w in t.lower() for w in ('declin','refus')) else [0.,1.] + [0.] * 1022 for t in texts]
    class Graph:
        def sync(self, *args):
            pass
    async def extract(*args):
        return ExtractedKnowledge(mentions=[], claims=[]), {'input_tokens': 0, 'output_tokens': 0, 'estimated_cost': 0}
    monkeypatch.setattr(extraction, 'extract', extract)
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        command.upgrade(migration_config(connection), 'head')
    factory = sessionmaker(engine, expire_on_commit=False)
    config = Settings.model_construct(database_url=postgres_url)
    with factory() as db:
        book = Book(title='Vector and keyword test')
        db.add(book); db.flush()
        reading = ReadingSession(book_id=book.id, page_label='1–2', image_path='synthetic', extraction={
            'left': 'Helenka declined the proposal because the players needed rest.',
            'right': 'The tournament took place in 1972.', 'readable': True})
        db.add(reading); db.flush()
        job = KnowledgeRepository(db).enqueue(reading, config.embedding_model)
        db.commit()
        job_id, book_id = job.id, book.id
    await KnowledgeProcessor(factory, config, Encoder(), Graph()).run(job_id)
    with factory() as db:
        repo = KnowledgeRepository(db)
        semantic = repo.search(book_id, 'refused', Encoder().encode(['refused'])[0], None, None)
        assert 'declined' in semantic[0].text
        keyword = repo.search(book_id, '1972', None, None, None)
        assert len(keyword) == 1 and '1972' in keyword[0].text
        assert repo.search(book_id, '1972', None, 1, 1) == []
    engine.dispose()
