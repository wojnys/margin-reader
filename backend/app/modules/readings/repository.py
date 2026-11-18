from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.modules.readings.models import ReadingSession, StepResult
from backend.app.modules.vocabulary.models import Vocabulary, VocabularySource


class ReadingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, reading_id: str) -> ReadingSession | None:
        return self.db.get(ReadingSession, reading_id)

    def list(
        self, book_id: str, *, completed: bool = False, limit: int | None = None
    ) -> list[ReadingSession]:
        query = (
            select(ReadingSession)
            .where(ReadingSession.book_id == book_id)
            .order_by(
                ReadingSession.created_at.desc(), ReadingSession.batch_position.asc(), ReadingSession.id
            )
        )
        if completed:
            query = query.where(ReadingSession.status == "complete")
        if limit is not None:
            query = query.limit(limit)
        return list(self.db.scalars(query))

    def sample(self) -> ReadingSession | None:
        return self.db.scalar(select(ReadingSession).where(ReadingSession.image_path == "sample"))

    def add(self, reading: ReadingSession) -> ReadingSession:
        self.db.add(reading)
        self.db.flush()
        return reading

    def steps(self, reading_id: str) -> list[StepResult]:
        return list(self.db.scalars(select(StepResult).where(StepResult.session_id == reading_id)))

    def cached_step(self, reading_id: str, revision: int, stage: str) -> StepResult | None:
        return self.db.scalar(
            select(StepResult).where(
                StepResult.session_id == reading_id,
                StepResult.revision == revision,
                StepResult.stage == stage,
            )
        )

    def add_step(self, result: StepResult) -> None:
        self.db.add(result)
        self.db.flush()

    def saved_expressions(self, reading_id: str, revision: int) -> list[str]:
        return list(
            self.db.scalars(
                select(Vocabulary.expression)
                .join(VocabularySource, VocabularySource.vocabulary_id == Vocabulary.id)
                .where(VocabularySource.session_id == reading_id, VocabularySource.revision == revision)
            )
        )

    def pending(self) -> list[ReadingSession]:
        return list(
            self.db.scalars(select(ReadingSession).where(ReadingSession.status == "pending").limit(10))
        )

    def mark_queued(self, reading_id: str, revision: int) -> None:
        self.db.execute(
            update(ReadingSession)
            .where(
                ReadingSession.id == reading_id,
                ReadingSession.revision == revision,
                ReadingSession.status == "pending",
            )
            .values(status="queued")
        )
