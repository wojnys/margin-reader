from __future__ import annotations

from pydantic import JsonValue
from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, uid


class ConversationSet(Base):
    __tablename__ = "conversation_sets"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("session_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("reading_sessions.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)


class ConversationExpression(Base):
    __tablename__ = "conversation_expressions"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("set_id", "source_index"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    set_id: Mapped[str] = mapped_column(ForeignKey("conversation_sets.id"), index=True)
    source_index: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
