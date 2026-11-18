from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from pydantic import JsonValue
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, now, uid
from backend.app.modules.knowledge.schemas import EntityKind


class IndexJob(Base):
    __tablename__ = "knowledge_jobs"
    __table_args__: tuple[UniqueConstraint, ...] = (
        UniqueConstraint("session_id", "content_hash", "pipeline_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("reading_sessions.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    pipeline_version: Mapped[str] = mapped_column(String(30), default="knowledge-v1")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    stages: Mapped[dict[str, JsonValue]] = mapped_column(JSON, default=dict)
    embedding_model: Mapped[str] = mapped_column(String(200), default="Qwen/Qwen3-Embedding-0.6B")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SourcePage(Base):
    __tablename__ = "knowledge_pages"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("job_id", "side"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("knowledge_jobs.id"), index=True)
    side: Mapped[str] = mapped_column(String(5))
    page_label: Mapped[str] = mapped_column(String(100))
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class Passage(Base):
    __tablename__ = "knowledge_passages"
    __table_args__: tuple[UniqueConstraint, Index] = (
        UniqueConstraint("page_id", "position"),
        Index("ix_knowledge_passages_keywords", "keywords", postgresql_using="gin").ddl_if(
            dialect="postgresql"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    page_id: Mapped[str] = mapped_column(ForeignKey("knowledge_pages.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024).with_variant(JSON(), "sqlite"))
    keywords: Mapped[str | None] = mapped_column(TSVECTOR().with_variant(Text(), "sqlite"))


class KnowledgeEntity(Base):
    __tablename__ = "knowledge_entities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[EntityKind] = mapped_column(String(30))


class Mention(Base):
    __tablename__ = "knowledge_mentions"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("job_id", "local_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("knowledge_jobs.id"), index=True)
    local_id: Mapped[str] = mapped_column(String(60))
    passage_id: Mapped[str] = mapped_column(ForeignKey("knowledge_passages.id"))
    surface: Mapped[str] = mapped_column(Text)
    kind: Mapped[EntityKind] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    named: Mapped[bool]
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_entities.id"), index=True)
    resolution: Mapped[str] = mapped_column(String(30), default="unresolved")
    evidence: Mapped[list[JsonValue]] = mapped_column(JSON, default=list)


class KnowledgeClaim(Base):
    __tablename__ = "knowledge_claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("knowledge_jobs.id"), index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey("knowledge_mentions.id"))
    object_id: Mapped[str] = mapped_column(ForeignKey("knowledge_mentions.id"))
    relation: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[JsonValue]] = mapped_column(JSON, default=list)


class KnowledgeSummary(Base):
    __tablename__ = "knowledge_summaries"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("job_id", "side"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("knowledge_jobs.id"), index=True)
    side: Mapped[str] = mapped_column(String(5))
    text: Mapped[str] = mapped_column(Text)


class SectionSummary(Base):
    __tablename__ = "knowledge_sections"
    __table_args__: tuple[UniqueConstraint, ...] = (UniqueConstraint("book_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    level: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    leaves: Mapped[list[JsonValue]] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(Text)
