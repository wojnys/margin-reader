"""Durable processing service. Database access stays in ReadingRepository."""

from __future__ import annotations

import asyncio
from typing import Literal

from openai import APIStatusError
from pydantic import BaseModel
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from sqlalchemy.exc import IntegrityError
from temporalio.exceptions import ApplicationError

from backend.app.ai import client as ai
from backend.app.ai.schemas import ExtractedPages
from backend.app.core.config import Settings
from backend.app.db.session import SessionFactory, UnitOfWork
from backend.app.modules.readings.models import ReadingSession, StepResult
from backend.app.modules.readings.ocr import OcrError, extract_pages
from backend.app.modules.readings.repository import ReadingRepository
from backend.app.temporal.workflows import FailedJob, ReadingJob

Stage = Literal["extract", "translate", "teach"]
STAGES = {"extract": "reading", "translate": "translating", "teach": "learning"}


def provider_rejection_detail(exc: APIStatusError | ModelHTTPError) -> str:
    """Expose the provider's validation reason, never request headers or credentials."""
    detail = str(exc)
    return detail[:500] if detail else "No validation detail was returned."


def check_readable(extraction: ExtractedPages) -> None:
    if not extraction.readable or not extraction.left.strip() or not extraction.right.strip():
        raise ApplicationError(
            "Both pages need to be readable. Try a clearer photograph, or correct the extracted text.",
            type="UnreadablePhoto",
            non_retryable=True,
        )


def current(repository: ReadingRepository, job: ReadingJob) -> ReadingSession:
    reading = repository.get(job["session_id"])
    if reading is None or reading.revision != job["revision"]:
        raise ApplicationError("This reading was replaced by a newer revision", non_retryable=True)
    return reading


class ReadingProcessor:
    def __init__(self, sessions: SessionFactory, config: Settings) -> None:
        self.sessions = sessions
        self.config = config

    async def process_stage(self, job: ReadingJob, stage: Stage) -> None:
        with self.sessions() as db:
            repository = ReadingRepository(db)
            reading = current(repository, job)
            cached = repository.cached_step(reading.id, reading.revision, stage)
            if cached is not None:
                if stage == "extract":
                    check_readable(ExtractedPages.model_validate(cached.result))
                return
            if stage == "extract" and reading.extraction is not None:
                check_readable(ExtractedPages.model_validate(reading.extraction))
                return
            reading.status, reading.error = STAGES[stage], None
            image_path, raw_extraction, context = reading.image_path, reading.extraction, reading.context
            UnitOfWork(db).commit()
        try:
            output: BaseModel
            if stage == "extract":
                output = await asyncio.to_thread(extract_pages, self.config.data_dir / "uploads" / image_path)
                metrics = {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0}
            else:
                extraction = ExtractedPages.model_validate(raw_extraction)
                if stage == "translate":
                    output, metrics = await ai.translate(extraction, context, config=self.config)
                else:
                    output, metrics = await ai.teach(extraction, context, config=self.config)
        except (APIStatusError, ModelHTTPError) as exc:
            if exc.status_code in {400, 401, 402, 403, 404, 413, 422}:
                raise ApplicationError(
                    f"DeepInfra rejected the request (HTTP {exc.status_code}): {provider_rejection_detail(exc)}",
                    non_retryable=True,
                ) from None
            raise ApplicationError(
                "DeepInfra is temporarily unavailable; the request will be retried"
            ) from None
        except ModelAPIError:
            raise ApplicationError(
                "DeepInfra timed out or could not be reached. The saved stage will be retried."
            ) from None
        except UnexpectedModelBehavior as exc:
            raise ApplicationError(
                f"The AI response could not be validated: {str(exc)[:400]}. The stage will be retried."
            ) from None
        except ai.ConfigurationError:
            raise ApplicationError(
                "Add a valid DEEPINFRA_API_KEY to .env and restart the API and worker", non_retryable=True
            ) from None
        except OcrError as exc:
            raise ApplicationError(
                "Local OCR could not read the photograph. The saved stage will be retried."
            ) from exc
        payload = output.model_dump(mode="json")
        with self.sessions() as db:
            repository = ReadingRepository(db)
            reading = current(repository, job)
            try:
                if stage == "extract":
                    reading.extraction = payload
                    if self.config.knowledge_enabled:
                        from backend.app.modules.knowledge.repository import KnowledgeRepository

                        KnowledgeRepository(db).enqueue(reading, self.config.embedding_model)
                elif stage == "translate":
                    reading.translation = payload
                else:
                    reading.learning = payload
                repository.add_step(
                    StepResult(
                        session_id=reading.id,
                        revision=reading.revision,
                        stage=stage,
                        model="local-rapidocr" if stage == "extract" else self.config.deepinfra_model,
                        prompt_version="ocr-v1" if stage == "extract" else ai.PROMPT_VERSION,
                        result=payload,
                        input_tokens=metrics["input_tokens"],
                        output_tokens=metrics["output_tokens"],
                        estimated_cost=metrics["estimated_cost"],
                    )
                )
                UnitOfWork(db).commit()
            except IntegrityError:
                UnitOfWork(db).rollback()
        if stage == "extract":
            check_readable(ExtractedPages.model_validate(payload))

    def finish(self, job: ReadingJob) -> None:
        with self.sessions() as db:
            reading = current(ReadingRepository(db), job)
            reading.status, reading.error = "complete", None
            UnitOfWork(db).commit()

    def fail(self, job: FailedJob) -> None:
        with self.sessions() as db:
            reading = ReadingRepository(db).get(job["session_id"])
            if reading and reading.revision == job["revision"]:
                reading.status, reading.error = "failed", job["message"]
                UnitOfWork(db).commit()
