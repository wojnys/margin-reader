from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.modules.books.models import Book
from backend.app.modules.chat.models import ChatThread, ChatTurn
from backend.app.modules.readings.models import ReadingSession


class ChatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def book(self, book_id: str) -> Book | None:
        return self.db.get(Book, book_id)

    def thread(self, thread_id: str) -> ChatThread | None:
        return self.db.get(ChatThread, thread_id)

    def threads(self, book_id: str) -> list[ChatThread]:
        return list(
            self.db.scalars(
                select(ChatThread)
                .where(ChatThread.book_id == book_id)
                .order_by(ChatThread.created_at.desc(), ChatThread.id)
            )
        )

    def turns(self, thread_id: str) -> list[ChatTurn]:
        return list(
            self.db.scalars(
                select(ChatTurn)
                .where(ChatTurn.thread_id == thread_id)
                .order_by(ChatTurn.created_at, ChatTurn.id)
            )
        )

    def turn(self, turn_id: str) -> ChatTurn | None:
        return self.db.get(ChatTurn, turn_id)

    def requested(self, thread_id: str, request_id: str) -> ChatTurn | None:
        return self.db.scalar(
            select(ChatTurn).where(ChatTurn.thread_id == thread_id, ChatTurn.request_id == request_id)
        )

    def readings(self, book_id: str) -> list[ReadingSession]:
        return list(
            self.db.scalars(
                select(ReadingSession)
                .where(ReadingSession.book_id == book_id, ReadingSession.extraction.is_not(None))
                .order_by(ReadingSession.created_at, ReadingSession.batch_position, ReadingSession.id)
            )
        )

    def add_thread(self, item: ChatThread) -> ChatThread:
        self.db.add(item)
        self.db.flush()
        return item

    def add_turn(self, item: ChatTurn) -> ChatTurn:
        self.db.add(item)
        self.db.flush()
        return item

    def claim(self, thread_id: str, turn_id: str) -> bool:
        return (
            self.db.execute(
                update(ChatThread)
                .where(ChatThread.id == thread_id, ChatThread.active_turn_id.is_(None))
                .values(active_turn_id=turn_id)
                .returning(ChatThread.id)
            ).scalar_one_or_none()
            is not None
        )

    def release(self, thread_id: str, turn_id: str) -> None:
        self.db.execute(
            update(ChatThread)
            .where(ChatThread.id == thread_id, ChatThread.active_turn_id == turn_id)
            .values(active_turn_id=None)
        )

    def pending(self) -> list[ChatTurn]:
        return list(self.db.scalars(select(ChatTurn).where(ChatTurn.status == "pending").limit(10)))

    def mark_queued(self, turn_id: str, attempt: int) -> None:
        self.db.execute(
            update(ChatTurn)
            .where(ChatTurn.id == turn_id, ChatTurn.attempt == attempt, ChatTurn.status == "pending")
            .values(status="queued")
        )
