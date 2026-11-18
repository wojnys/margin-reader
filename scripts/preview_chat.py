"""Isolated UI smoke-test server. Synthetic content, dummy settings, no paid provider calls.

Run `.venv/bin/python -m scripts.preview_chat`, then open http://localhost:8097.
The temporary database is deliberately separate from the application's data directory.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from pydantic import JsonValue, SecretStr

from backend.app import sample
from backend.app.ai import chat as ai
from backend.app.ai.client import Metrics
from backend.app.core.config import Settings
from backend.app.core.runtime import Runtime, RuntimeApp
from backend.app.db.base import Base
from backend.app.db.session import create_database
from backend.app.knowledge import retrieval
from backend.app.main import create_app
from backend.app.modules.books.models import Book
from backend.app.modules.chat.processing import ChatProcessor
from backend.app.modules.chat.repository import ChatRepository
from backend.app.modules.chat.schemas import AnswerCitation, BookAnswer, SourcePassage
from backend.app.modules.knowledge.models import KnowledgeEntity, Mention
from backend.app.modules.knowledge.repository import KnowledgeRepository
from backend.app.modules.knowledge.schemas import RetrievalPlan
from backend.app.modules.readings.models import ReadingSession


async def fake_answer(
    question: str,
    sources: list[SourcePassage],
    history: list[JsonValue],
    title: str,
    language: str,
    *,
    config: Settings,
) -> tuple[BookAnswer, Metrics]:
    await asyncio.sleep(0.2)
    source = sources[0]
    return BookAnswer(
        answer="Anna finds a green notebook. Its message encourages her to notice ordinary things around her.\n\nThis is a prepared English reply for the offline interface preview, not a live model answer.",
        supported=True,
        citations=[AnswerCitation(source_id=source.id, quote=source.text[:90])],
    ), {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0}


async def preview_plan(
    question: str, history: list[JsonValue], config: Settings
) -> tuple[RetrievalPlan, Metrics]:
    return RetrievalPlan(strategy="passages", query=question), {
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": 0,
    }


def preview_app() -> RuntimeApp:
    directory = Path(tempfile.mkdtemp(prefix="margin-chat-preview-"))
    config = Settings.model_construct(
        data_dir=directory,
        database_url=f"sqlite:///{directory / 'preview.db'}",
        deepinfra_api_key=SecretStr("dummy-preview-key"),
    )
    sessions = create_database(config.database_url)
    with sessions() as db:
        bind = db.get_bind()
        Base.metadata.create_all(bind)
        book = Book(title="The Green Notebook", author="Offline preview", level="B2")
        db.add(book)
        db.flush()
        reading = ReadingSession(
            book_id=book.id,
            page_label="1–2",
            image_path="sample",
            status="complete",
            context={},
            extraction={"left": sample.LEFT, "right": sample.RIGHT, "readable": True},
            learning=sample.LEARNING,
        )
        db.add(reading)
        db.flush()
        repo = KnowledgeRepository(db)
        job = repo.enqueue(reading, config.embedding_model)
        assert job is not None
        repo.prepare(job)
        job.status = "ready"
        entity = KnowledgeEntity(book_id=book.id, name="Anna", kind="person")
        db.add(entity)
        db.flush()
        passage = repo.passages(job.id)[0]
        db.add(
            Mention(
                job_id=job.id,
                local_id="preview-anna",
                passage_id=passage.id,
                surface="Anna",
                kind="person",
                description="Anna in the synthetic story",
                named=True,
                entity_id=entity.id,
                resolution="explicit",
                evidence=[passage.id],
            )
        )
        db.add(
            Mention(
                job_id=job.id,
                local_id="preview-reference",
                passage_id=passage.id,
                surface="she",
                kind="person",
                description="A reference to review in the synthetic story.",
                named=False,
            )
        )
        db.commit()
    ai.answer_book = fake_answer
    retrieval.plan_question = preview_plan
    app = create_app(Runtime(config, sessions, "isolated-preview-owner"), background_jobs=False)
    processor = ChatProcessor(sessions, config)

    @asynccontextmanager
    async def lifespan(_: RuntimeApp) -> AsyncIterator[None]:
        async def work() -> None:
            while True:
                with sessions() as db:
                    for job in KnowledgeRepository(db).pending():
                        job.status = "ready"  # UI preview only: never invoke real index/model services.
                    db.commit()
                    ids = [item.id for item in ChatRepository(db).pending()]
                for turn_id in ids:
                    await processor.generate(turn_id)
                await asyncio.sleep(0.1)

        task = asyncio.create_task(work())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app.router.lifespan_context = lifespan
    return app


if __name__ == "__main__":
    uvicorn.run(preview_app(), host="127.0.0.1", port=8097)
