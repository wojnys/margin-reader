from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, now, uid


class Vocabulary(Base):
    __tablename__ = "vocabulary"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    identity: Mapped[str] = mapped_column(String(64), unique=True)
    expression: Mapped[str] = mapped_column(String(300))
    meaning_cs: Mapped[str] = mapped_column(Text)
    explanation_cs: Mapped[str] = mapped_column(Text)
    example_en: Mapped[str] = mapped_column(Text)
    example_cs: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40))
    level: Mapped[str] = mapped_column(String(2))
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class VocabularySource(Base):
    __tablename__ = "vocabulary_sources"
    __table_args__: tuple[UniqueConstraint, ...] = (
        UniqueConstraint("vocabulary_id", "session_id", "revision"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    vocabulary_id: Mapped[str] = mapped_column(ForeignKey("vocabulary.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("reading_sessions.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    source_sentence: Mapped[str] = mapped_column(Text)
    page_side: Mapped[str] = mapped_column(String(5))
