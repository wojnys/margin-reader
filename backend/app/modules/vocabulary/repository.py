from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import now
from backend.app.modules.books.models import Book
from backend.app.modules.readings.models import ReadingSession
from backend.app.modules.vocabulary.models import Vocabulary, VocabularySource


class VocabularyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, item_id: str, *, for_update: bool = False) -> Vocabulary | None:
        query = select(Vocabulary).where(Vocabulary.id == item_id)
        if for_update:
            query = query.with_for_update()
        return self.db.scalar(query)

    def by_identity(self, identity: str) -> Vocabulary | None:
        return self.db.scalar(select(Vocabulary).where(Vocabulary.identity == identity))

    def list(self, *, due: bool = False) -> list[Vocabulary]:
        query = select(Vocabulary).order_by(Vocabulary.due_at if due else Vocabulary.created_at.desc())
        if due:
            query = query.where(Vocabulary.due_at <= now())
        return list(self.db.scalars(query))

    def add(self, item: Vocabulary) -> Vocabulary:
        self.db.add(item)
        self.db.flush()
        return item

    def has_source(self, item_id: str, reading_id: str, revision: int) -> bool:
        return (
            self.db.scalar(
                select(VocabularySource.id).where(
                    VocabularySource.vocabulary_id == item_id,
                    VocabularySource.session_id == reading_id,
                    VocabularySource.revision == revision,
                )
            )
            is not None
        )

    def add_source(self, source: VocabularySource) -> None:
        self.db.add(source)
        self.db.flush()

    def source_context(self, item_id: str) -> tuple[str, str]:
        row = self.db.execute(
            select(VocabularySource.source_sentence, Book.title)
            .join(ReadingSession, VocabularySource.session_id == ReadingSession.id)
            .join(Book, ReadingSession.book_id == Book.id)
            .where(VocabularySource.vocabulary_id == item_id)
            .order_by(VocabularySource.id)
            .limit(1)
        ).first()
        return (row[0], row[1]) if row else ("", "")
