from __future__ import annotations

from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, now, uid


class ReadingSession(Base):
    __tablename__ = "reading_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), index=True)
    page_label: Mapped[str] = mapped_column(String(100), default="")
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    batch_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_path: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, JsonValue]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    knowledge_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    knowledge_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    extraction: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON, nullable=True)
    translation: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON, nullable=True)
    learning: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class StepResult(Base):
    __tablename__ = "step_results"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("session_id", "revision", "stage"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("reading_sessions.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(30), default="v1")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    result: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
