from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.modules.books.models import Book
from backend.app.modules.readings.models import ReadingSession


class BookRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, book_id: str) -> Book | None:
        return self.db.get(Book, book_id)

    def list(self) -> list[Book]:
        return list(self.db.scalars(select(Book).order_by(Book.created_at.desc())))

    def count_readings(self, book_id: str) -> int:
        return (
            self.db.scalar(
                select(func.count()).select_from(ReadingSession).where(ReadingSession.book_id == book_id)
            )
            or 0
        )

    def add(self, book: Book) -> Book:
        self.db.add(book)
        self.db.flush()
        return book
