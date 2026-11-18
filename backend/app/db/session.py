from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from importlib import import_module
from sqlite3 import Connection

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = Callable[[], AbstractContextManager[Session]]


def create_database(url: str) -> sessionmaker[Session]:
    # Workers construct sessions without importing the FastAPI application. Register every
    # model here so SQLAlchemy can resolve cross-feature foreign keys in that process too.
    import_module("backend.app.db.models")

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {},
        pool_pre_ping=True,
    )
    configure_engine(engine)
    return sessionmaker(engine, expire_on_commit=False)


def configure_engine(engine: Engine) -> None:
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection: Connection, _: object) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")


class UnitOfWork:
    """Services decide when a transaction commits; repositories only flush."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
