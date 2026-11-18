from __future__ import annotations

from openai import APIStatusError
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from sqlalchemy.exc import IntegrityError
from temporalio.exceptions import ApplicationError

from backend.app.ai import client as ai
from backend.app.ai.schemas import Learning
from backend.app.core.config import Settings
from backend.app.db.session import SessionFactory, UnitOfWork
from backend.app.modules.conversation.models import ConversationExpression, ConversationSet
from backend.app.modules.conversation.repository import ConversationRepository
from backend.app.modules.conversation.schemas import ConversationCard
from backend.app.modules.readings.models import StepResult
from backend.app.modules.readings.processing import current, provider_rejection_detail
from backend.app.modules.readings.repository import ReadingRepository
from backend.app.temporal.workflows import FailedJob, ReadingJob


class ConversationProcessor:
    def __init__(self, sessions: SessionFactory, config: Settings) -> None:
        self.sessions = sessions
        self.config = config

    async def generate(self, job: ReadingJob) -> None:
        with self.sessions() as db:
            reading_repository = ReadingRepository(db)
            reading = current(reading_repository, job)
            repository = ConversationRepository(db)
            item = repository.get(reading.id, reading.revision)
            if item is not None and item.status == "complete":
                return
            if not reading.learning:
                raise ApplicationError("Learning expressions must be ready first", non_retryable=True)
            learning = Learning.model_validate(reading.learning)
            if item is None:
                # Inline v3 generation starts directly in generating state. The independent
                # outbox dispatcher must never pick up this set and issue a duplicate call.
                item = repository.add(
                    ConversationSet(session_id=reading.id, revision=reading.revision, status="generating")
                )
            else:
                item.status, item.error = "generating", None
            UnitOfWork(db).commit()
        try:
            result, metrics = await ai.conversation(learning, config=self.config)
        except (APIStatusError, ModelHTTPError) as exc:
            raise ApplicationError(
                f"Conversation generation was rejected (HTTP {exc.status_code}): {provider_rejection_detail(exc)}",
                non_retryable=exc.status_code in {400, 401, 402, 403, 404, 413, 422},
            ) from None
        except ai.ConfigurationError:
            raise ApplicationError(
                "Configure DeepInfra before generating conversation examples", non_retryable=True
            ) from None
        except (ModelAPIError, UnexpectedModelBehavior):
            raise ApplicationError(
                "Conversation examples could not be generated or validated; the activity will retry"
            ) from None
        with self.sessions() as db:
            reading_repository = ReadingRepository(db)
            reading = current(reading_repository, job)
            repository = ConversationRepository(db)
            item = repository.get(reading.id, reading.revision)
            if item is None:
                raise ApplicationError("Conversation job is missing", non_retryable=True)
            if item.status == "complete":
                return
            try:
                for generated in result.cards:
                    source = learning.expressions[generated.source_index]
                    card = ConversationCard.model_validate(
                        {
                            **generated.model_dump(),
                            "expression": source.expression,
                            "source_sentence": source.source_sentence,
                            "page_side": source.page_side,
                        }
                    )
                    repository.add_card(
                        ConversationExpression(
                            set_id=item.id,
                            source_index=generated.source_index,
                            payload=card.model_dump(mode="json"),
                        )
                    )
                item.status, item.error = "complete", None
                reading_repository.add_step(
                    StepResult(
                        session_id=reading.id,
                        revision=reading.revision,
                        stage="conversation",
                        model=self.config.deepinfra_model,
                        prompt_version="conversation-v1",
                        result=result.model_dump(mode="json"),
                        **metrics,
                    )
                )
                UnitOfWork(db).commit()
            except IntegrityError:
                UnitOfWork(db).rollback()

    def fail(self, job: FailedJob) -> None:
        with self.sessions() as db:
            repository = ConversationRepository(db)
            item = repository.get(job["session_id"], job["revision"])
            if item is not None and item.status != "complete":
                item.status, item.error = "failed", job["message"]
                UnitOfWork(db).commit()
