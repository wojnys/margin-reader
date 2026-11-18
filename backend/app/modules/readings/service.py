from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import JsonValue

from backend.app import sample
from backend.app.ai.schemas import ExtractedPages, Learning, Translation
from backend.app.core.config import Settings
from backend.app.core.exceptions import DomainError
from backend.app.db.base import uid
from backend.app.db.session import UnitOfWork
from backend.app.modules.books.service import BookService
from backend.app.modules.conversation.service import ConversationService
from backend.app.modules.readings.images import normalized_image
from backend.app.modules.readings.models import ReadingSession
from backend.app.modules.readings.repository import ReadingRepository
from backend.app.modules.readings.schemas import (
    CorrectText,
    ReadingResponse,
    RefreshLearning,
    SampleResponse,
    UsageResponse,
)

ACTIVE_STATUSES = {"pending", "queued", "reading", "translating", "learning"}


class ReadingService:
    def __init__(self, uow: UnitOfWork, config: Settings) -> None:
        self.uow = uow
        self.config = config
        self.repository = ReadingRepository(uow.session)
        self.books = BookService(uow)

    def require(self, reading_id: str) -> ReadingSession:
        reading = self.repository.get(reading_id)
        if reading is None:
            raise DomainError(404, "Reading not found")
        return reading

    def response(self, reading: ReadingSession) -> ReadingResponse:
        steps = self.repository.steps(reading.id)
        return ReadingResponse(
            id=reading.id,
            book_id=reading.book_id,
            page_label=reading.page_label,
            batch_id=reading.batch_id,
            batch_position=reading.batch_position,
            status=reading.status,
            error=reading.error,
            revision=reading.revision,
            created_at=reading.created_at.isoformat() + "Z",
            extraction=ExtractedPages.model_validate(reading.extraction) if reading.extraction else None,
            translation=Translation.model_validate(reading.translation) if reading.translation else None,
            learning=Learning.model_validate(reading.learning) if reading.learning else None,
            conversation=ConversationService(self.uow).response(reading.id, reading.revision),
            saved_expressions=self.repository.saved_expressions(reading.id, reading.revision),
            is_sample=reading.image_path == "sample",
            usage=UsageResponse(
                input_tokens=sum(s.input_tokens for s in steps),
                output_tokens=sum(s.output_tokens for s in steps),
                estimated_cost=sum(s.estimated_cost for s in steps),
            ),
        )

    def list(self, book_id: str) -> list[ReadingResponse]:
        self.books.require(book_id)
        return [self.response(reading) for reading in self.repository.list(book_id)]

    def sample(self) -> SampleResponse:
        existing = self.repository.sample()
        if existing:
            return SampleResponse(book_id=existing.book_id, session_id=existing.id)
        from backend.app.modules.books.models import Book

        book = self.books.repository.add(
            Book(title="The Green Notebook", author="An original Margin sample", level="B2")
        )
        reading = self.repository.add(
            ReadingSession(
                book_id=book.id,
                page_label="1–2",
                image_path="sample",
                status="complete",
                context={"sample": True},
                extraction={"left": sample.LEFT, "right": sample.RIGHT, "readable": True, "warnings": []},
                translation=None,
                learning=sample.LEARNING,
            )
        )
        result = SampleResponse(book_id=book.id, session_id=reading.id)
        self.uow.commit()
        return result

    async def prepare_upload(
        self,
        book_id: str,
        content: bytes,
        page_label: str,
        *,
        context_snapshot: dict[str, JsonValue] | None = None,
    ) -> ReadingSession:
        book = self.books.require(book_id)
        if not self.config.deepinfra_api_key.get_secret_value():
            raise DomainError(409, "Add DEEPINFRA_API_KEY to .env and restart the app before uploading")
        if len(content) > 20 * 1024 * 1024:
            raise DomainError(413, "The photograph must be smaller than 20 MB")
        normalized = await asyncio.to_thread(normalized_image, content)
        previous = self.repository.list(book_id, completed=True, limit=3)
        summaries: list[JsonValue] = []
        for session in reversed(previous):
            if not session.learning:
                continue
            learning = Learning.model_validate(session.learning)
            summary = " ".join(
                part
                for part in (learning.left_summary_en, learning.right_summary_en, learning.summary_cs)
                if part
            )
            if summary:
                summaries.append(summary)
        filename = f"{uid()}.jpg"
        path = self.config.data_dir / "uploads" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(normalized)
        try:
            return self.repository.add(
                ReadingSession(
                    id=uid(),
                    book_id=book_id,
                    page_label=page_label[:100],
                    image_path=filename,
                    context=context_snapshot
                    if context_snapshot is not None
                    else {
                        "title": book.title,
                        "author": book.author,
                        "level": book.level,
                        "reader_notes": book.notes,
                        "prior_summaries": summaries,
                    },
                )
            )
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    async def upload(self, book_id: str, content: bytes, page_label: str) -> ReadingResponse:
        reading = await self.prepare_upload(book_id, content, page_label)
        try:
            result = self.response(reading)
            self.uow.commit()
            return result
        except BaseException:
            self.remove_upload(reading)
            raise

    def remove_upload(self, reading: ReadingSession) -> None:
        (self.config.data_dir / "uploads" / reading.image_path).unlink(missing_ok=True)

    def image(self, reading_id: str) -> Path:
        reading = self.require(reading_id)
        path = self.config.data_dir / "uploads" / reading.image_path
        if reading.image_path == "sample" or not path.is_file():
            raise DomainError(404, "Photograph not found")
        return path

    def retry(self, reading_id: str) -> ReadingResponse:
        reading = self.require(reading_id)
        if reading.status != "failed":
            raise DomainError(409, "Only a failed reading can be retried")
        reading.attempt += 1
        reading.status, reading.error = "pending", None
        return self.commit_response(reading)

    def refresh_learning(self, reading_id: str, body: RefreshLearning) -> ReadingResponse:
        reading = self.require(reading_id)
        self.check_revision(reading, body.revision)
        if reading.image_path == "sample":
            raise DomainError(
                409, "The prepared tutorial is fixed. Upload your own pages to generate expressions."
            )
        if reading.extraction is None:
            raise DomainError(409, "A transcription is needed before refreshing expressions")
        reading.revision += 1
        reading.learning, reading.error = None, None
        reading.status = "pending"
        return self.commit_response(reading)

    def correct_text(self, reading_id: str, body: CorrectText) -> ReadingResponse:
        reading = self.require(reading_id)
        self.check_revision(reading, body.revision)
        reading.revision += 1
        reading.extraction = {"left": body.left, "right": body.right, "readable": True, "warnings": []}
        if self.config.knowledge_enabled:
            from backend.app.modules.knowledge.repository import KnowledgeRepository

            KnowledgeRepository(self.uow.session).enqueue(reading, self.config.embedding_model)
        reading.translation, reading.learning, reading.error = None, None, None
        reading.status = "pending"
        return self.commit_response(reading)

    def check_revision(self, reading: ReadingSession, revision: int) -> None:
        if reading.status in ACTIVE_STATUSES or reading.revision != revision:
            raise DomainError(409, "Wait for processing to finish and refresh before editing or regenerating")

    def commit_response(self, reading: ReadingSession) -> ReadingResponse:
        result = self.response(reading)
        self.uow.commit()
        return result
