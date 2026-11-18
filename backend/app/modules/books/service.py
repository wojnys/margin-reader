from __future__ import annotations

from backend.app.core.exceptions import DomainError
from backend.app.db.session import UnitOfWork
from backend.app.modules.books.models import Book
from backend.app.modules.books.repository import BookRepository
from backend.app.modules.books.schemas import BookInput, BookResponse


class BookService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.repository = BookRepository(uow.session)

    def require(self, book_id: str) -> Book:
        book = self.repository.get(book_id)
        if book is None:
            raise DomainError(404, "Book not found")
        return book

    def response(self, book: Book) -> BookResponse:
        return BookResponse(
            id=book.id,
            title=book.title,
            author=book.author,
            level=book.level,
            notes=book.notes,
            session_count=self.repository.count_readings(book.id),
        )

    def list(self) -> list[BookResponse]:
        return [self.response(book) for book in self.repository.list()]

    def create(self, body: BookInput) -> BookResponse:
        book = self.repository.add(
            Book(title=body.title, author=body.author, level=body.level, notes=body.notes)
        )
        result = self.response(book)
        self.uow.commit()
        return result
