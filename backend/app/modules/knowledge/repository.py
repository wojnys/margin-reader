from __future__ import annotations

import hashlib

from pgvector.sqlalchemy import Vector
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from backend.app.ai.schemas import ExtractedPages, Learning
from backend.app.db.base import uid
from backend.app.knowledge.chunking import chunks, content_hash, page_numbers
from backend.app.modules.chat.schemas import SourcePassage
from backend.app.modules.knowledge.models import (
    IndexJob,
    KnowledgeClaim,
    KnowledgeEntity,
    KnowledgeSummary,
    Mention,
    Passage,
    SourcePage,
)
from backend.app.modules.readings.models import ReadingSession


class KnowledgeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(self, reading: ReadingSession, model: str) -> IndexJob | None:
        if not reading.extraction:
            return None
        digest = content_hash(reading)
        version = "v1-" + hashlib.sha256(model.encode()).hexdigest()[:12]
        reading.knowledge_hash = digest
        item = self.db.scalar(
            select(IndexJob).where(
                IndexJob.session_id == reading.id,
                IndexJob.content_hash == digest,
                IndexJob.pipeline_version == version,
            )
        )
        if item is None:
            item = IndexJob(
                book_id=reading.book_id,
                session_id=reading.id,
                revision=reading.revision,
                content_hash=digest,
                embedding_model=model,
                pipeline_version=version,
            )
            self.db.add(item)
            self.db.flush()
        reading.knowledge_job_id = item.id
        return item

    def jobs(self, book_id: str) -> list[IndexJob]:
        return list(
            self.db.scalars(
                select(IndexJob)
                .join(ReadingSession, ReadingSession.id == IndexJob.session_id)
                .where(IndexJob.book_id == book_id, IndexJob.id == ReadingSession.knowledge_job_id)
                .order_by(IndexJob.created_at)
            )
        )

    def pending(self) -> list[IndexJob]:
        return list(self.db.scalars(select(IndexJob).where(IndexJob.status == "pending").limit(10)))

    def job(self, job_id: str) -> IndexJob | None:
        return self.db.get(IndexJob, job_id)

    def prepare(self, job: IndexJob) -> None:
        if self.db.scalar(select(SourcePage.id).where(SourcePage.job_id == job.id).limit(1)):
            return
        reading = self.db.get(ReadingSession, job.session_id)
        if reading is None or content_hash(reading) != job.content_hash:
            raise ValueError("This source was replaced by a newer text revision")
        extracted = ExtractedPages.model_validate(reading.extraction)
        numbers = page_numbers(reading.page_label)
        for side, text, number in (
            ("left", extracted.left, numbers[0]),
            ("right", extracted.right, numbers[1]),
        ):
            page = SourcePage(
                id=uid(),
                job_id=job.id,
                side=side,
                page_label=reading.page_label,
                page_number=number,
                text=text,
            )
            self.db.add(page)
            self.db.flush()
            for position, (start, end, value) in enumerate(chunks(text)):
                self.db.add(Passage(page_id=page.id, position=position, start=start, end=end, text=value))
        if reading.learning:
            learning = Learning.model_validate(reading.learning)
            for side, value in (("left", learning.left_summary_en), ("right", learning.right_summary_en)):
                if value:
                    self.db.add(KnowledgeSummary(job_id=job.id, side=side, text=value))
        self.db.flush()

    def passages(self, job_id: str) -> list[Passage]:
        return list(
            self.db.scalars(
                select(Passage)
                .join(SourcePage)
                .where(SourcePage.job_id == job_id)
                .order_by(SourcePage.side, Passage.position)
            )
        )

    def sources(
        self, book_id: str, start: int | None = None, end: int | None = None
    ) -> list[tuple[Passage, SourcePage, IndexJob]]:
        query = (
            select(Passage, SourcePage, IndexJob)
            .join(SourcePage, Passage.page_id == SourcePage.id)
            .join(IndexJob)
            .join(ReadingSession, ReadingSession.id == IndexJob.session_id)
            .where(IndexJob.book_id == book_id, IndexJob.id == ReadingSession.knowledge_job_id)
        )
        if start is not None:
            query = query.where(SourcePage.page_number >= start)
        if end is not None:
            query = query.where(SourcePage.page_number <= end)
        return [
            (p, page, job)
            for p, page, job in self.db.execute(
                query.order_by(
                    SourcePage.page_number, ReadingSession.created_at, SourcePage.side, Passage.position
                )
            )
        ]

    @staticmethod
    def source(passage: Passage, page: SourcePage, job: IndexJob) -> SourcePassage:
        return SourcePassage(
            id=passage.id,
            session_id=job.session_id,
            revision=job.revision,
            page_label=page.page_label,
            side="left" if page.side == "left" else "right",
            page_number=page.page_number,
            text=passage.text,
        )

    def entities(self, book_id: str) -> list[KnowledgeEntity]:
        return list(self.db.scalars(select(KnowledgeEntity).where(KnowledgeEntity.book_id == book_id)))

    def mentions(self, book_id: str) -> list[Mention]:
        return list(
            self.db.scalars(
                select(Mention)
                .join(IndexJob)
                .join(ReadingSession, ReadingSession.id == IndexJob.session_id)
                .where(IndexJob.book_id == book_id, IndexJob.id == ReadingSession.knowledge_job_id)
            )
        )

    def claims(self, book_id: str) -> list[KnowledgeClaim]:
        return list(
            self.db.scalars(
                select(KnowledgeClaim)
                .join(IndexJob)
                .join(ReadingSession, ReadingSession.id == IndexJob.session_id)
                .where(IndexJob.book_id == book_id, IndexJob.id == ReadingSession.knowledge_job_id)
            )
        )

    def lock_book(self, book_id: str) -> None:
        # Lock the stable parent row for the short reconciliation transaction only.
        from backend.app.modules.books.models import Book

        _ = self.db.scalar(select(Book).where(Book.id == book_id).with_for_update())

    def fill_keywords(self, passage: Passage) -> None:
        if self.db.get_bind().dialect.name == "postgresql":
            from sqlalchemy import update

            self.db.execute(
                update(Passage)
                .where(Passage.id == passage.id)
                .values(keywords=func.to_tsvector("english", passage.text))
            )
        else:
            passage.keywords = passage.text

    def search(
        self, book_id: str, query_text: str, vector: list[float] | None, start: int | None, end: int | None
    ) -> list[SourcePassage]:
        base = (
            select(Passage, SourcePage, IndexJob)
            .join(SourcePage, Passage.page_id == SourcePage.id)
            .join(IndexJob)
            .join(ReadingSession, ReadingSession.id == IndexJob.session_id)
            .where(IndexJob.book_id == book_id, IndexJob.id == ReadingSession.knowledge_job_id)
        )
        if start is not None:
            base = base.where(SourcePage.page_number >= start)
        if end is not None:
            base = base.where(SourcePage.page_number <= end)
        scored: dict[str, float] = {}
        sources: dict[str, SourcePassage] = {}
        if self.db.get_bind().dialect.name == "postgresql":
            query = func.websearch_to_tsquery("english", query_text)
            keyword = (
                base.where(Passage.keywords.op("@@")(query))
                .order_by(func.ts_rank_cd(Passage.keywords, query).desc())
                .limit(40)
            )
            searches = [keyword]
            if vector is not None:
                searches.append(
                    base.where(Passage.embedding.is_not(None))
                    .order_by(Passage.embedding.op("<=>")(literal(vector, type_=Vector(1024))))
                    .limit(40)
                )
            for statement in searches:
                for rank, (p, page, job) in enumerate(self.db.execute(statement)):
                    sources[p.id] = self.source(p, page, job)
                    scored[p.id] = scored.get(p.id, 0) + 1 / (60 + rank + 1)
        else:
            # SQLite is a small isolated-test fallback, not the production search engine.
            words = set(query_text.lower().split())
            rows = list(self.db.execute(base))
            keyword_rows = sorted(
                rows, key=lambda r: len(words & set(r[0].text.lower().split())), reverse=True
            )
            vector_rows = sorted(
                rows,
                key=lambda r: sum(a * b for a, b in zip(vector or [], r[0].embedding or [])),
                reverse=True,
            )
            for ranking in (keyword_rows[:40], vector_rows[:40] if vector else []):
                for rank, (p, page, job) in enumerate(ranking):
                    sources[p.id] = self.source(p, page, job)
                    scored[p.id] = scored.get(p.id, 0) + 1 / (60 + rank + 1)
        return [sources[pid] for pid in sorted(scored, key=lambda pid: scored[pid], reverse=True)]

    def by_ids(self, book_id: str, ids: list[str], start: int | None, end: int | None) -> list[SourcePassage]:
        # Revalidation against canonical current sources prevents stale/cross-book graph evidence.
        rows = self.sources(book_id, start, end)
        mapping = {p.id: self.source(p, page, job) for p, page, job in rows if p.id in ids}
        return [mapping[pid] for pid in ids if pid in mapping]
