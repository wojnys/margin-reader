from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    # UTC stored without timezone for consistent SQLite/PostgreSQL comparisons.
    return datetime.now(UTC).replace(tzinfo=None)
