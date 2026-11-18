from __future__ import annotations

from backend.app.core.exceptions import DomainError
from backend.app.db.base import uid
from backend.app.db.session import UnitOfWork
from backend.app.modules.chat.models import ChatThread, ChatTurn
from backend.app.modules.chat.repository import ChatRepository
from backend.app.modules.chat.schemas import (
    BookAnswer,
    CreateThread,
    SendMessage,
    SourcePassage,
    ThreadDetail,
    ThreadResponse,
    TurnResponse,
)


def turn_response(turn: ChatTurn) -> TurnResponse:
    return TurnResponse.model_validate(
        {
            "id": turn.id,
            "thread_id": turn.thread_id,
            "question": turn.question,
            "status": turn.status,
            "error": turn.error,
            "answer": BookAnswer.model_validate(turn.answer) if turn.answer else None,
            "sources": [SourcePassage.model_validate(source) for source in turn.sources],
            "source_count": turn.source_count,
            "input_tokens": turn.input_tokens,
            "output_tokens": turn.output_tokens,
            "estimated_cost": turn.estimated_cost,
            "created_at": turn.created_at.isoformat() + "Z",
            "retrieval_strategy": turn.retrieval.get("strategy"),
            "retrieval_notes": turn.retrieval.get("notes", []),
        }
    )


def thread_response(thread: ChatThread) -> ThreadResponse:
    return ThreadResponse.model_validate(
        {
            "id": thread.id,
            "book_id": thread.book_id,
            "title": thread.title,
            "language": "en",
            "created_at": thread.created_at.isoformat() + "Z",
        }
    )


class ChatService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.repository = ChatRepository(uow.session)

    def require_book(self, book_id: str) -> None:
        if self.repository.book(book_id) is None:
            raise DomainError(404, "Book not found")

    def require(self, thread_id: str) -> ChatThread:
        thread = self.repository.thread(thread_id)
        if thread is None:
            raise DomainError(404, "Chat not found")
        return thread

    def list(self, book_id: str) -> list[ThreadResponse]:
        self.require_book(book_id)
        return [thread_response(thread) for thread in self.repository.threads(book_id)]

    def create(self, book_id: str, body: CreateThread) -> ThreadResponse:
        self.require_book(book_id)
        thread = self.repository.add_thread(ChatThread(book_id=book_id, language="en"))
        self.uow.commit()
        return thread_response(thread)

    def detail(self, thread_id: str) -> ThreadDetail:
        thread = self.require(thread_id)
        return ThreadDetail.model_validate(
            {
                **thread_response(thread).model_dump(),
                "turns": [turn_response(turn) for turn in self.repository.turns(thread_id)],
            }
        )

    def send(self, thread_id: str, body: SendMessage) -> TurnResponse:
        thread = self.require(thread_id)
        question = body.question.strip()
        if not question:
            raise DomainError(422, "Write a question first")
        prior = self.repository.requested(thread_id, str(body.request_id))
        if prior:
            if prior.question != question or prior.scope != {
                "page_start": body.page_start,
                "page_end": body.page_end,
            }:
                raise DomainError(409, "This request identifier was already used for another question")
            return turn_response(prior)
        if not self.repository.readings(thread.book_id):
            raise DomainError(
                409, "Upload pages and wait for their text to be extracted before asking a question"
            )
        turn_id = uid()
        if not self.repository.claim(thread_id, turn_id):
            self.uow.rollback()
            raise DomainError(409, "Wait for the current reply before sending another question")
        turn = self.repository.add_turn(
            ChatTurn(
                id=turn_id,
                thread_id=thread_id,
                request_id=str(body.request_id),
                question=question,
                scope={"page_start": body.page_start, "page_end": body.page_end},
            )
        )
        if thread.title == "New conversation":
            thread.title = question[:120]
        self.uow.commit()
        return turn_response(turn)

    def retry(self, thread_id: str, turn_id: str) -> TurnResponse:
        self.require(thread_id)
        turn = self.repository.turn(turn_id)
        if turn is None or turn.thread_id != thread_id:
            raise DomainError(404, "Message not found in this chat")
        if turn.status != "failed":
            raise DomainError(409, "Only a failed reply can be retried")
        if not self.repository.claim(thread_id, turn_id):
            self.uow.rollback()
            raise DomainError(409, "Wait for the current reply")
        turn.status, turn.error, turn.attempt = "pending", None, turn.attempt + 1
        self.uow.commit()
        return turn_response(turn)
