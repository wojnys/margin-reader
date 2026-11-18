from __future__ import annotations

from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, now, uid


class ChatThread(Base):
    __tablename__ = "chat_threads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    language: Mapped[str] = mapped_column(String(2), default="en")
    active_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("thread_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    thread_id: Mapped[str] = mapped_column(ForeignKey("chat_threads.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    question: Mapped[str] = mapped_column(Text)
    scope: Mapped[dict[str, JsonValue]] = mapped_column(JSON, default=dict)
    retrieval: Mapped[dict[str, JsonValue]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON, nullable=True)
    sources: Mapped[list[JsonValue]] = mapped_column(JSON, default=list)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
