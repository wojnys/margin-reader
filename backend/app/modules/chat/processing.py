from __future__ import annotations

import json
import logging
from typing import cast

from openai import APIStatusError
from pydantic import JsonValue
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from temporalio import activity
from temporalio.exceptions import ApplicationError

from backend.app.ai import chat as ai
from backend.app.ai.client import ConfigurationError, Metrics
from backend.app.core.config import Settings
from backend.app.db.session import SessionFactory, UnitOfWork
from backend.app.modules.chat.context import passages, select_context
from backend.app.modules.chat.repository import ChatRepository
from backend.app.modules.chat.schemas import BookAnswer, SourcePassage
from backend.app.temporal.activities import with_heartbeats
from backend.app.temporal.chat_workflow import ChatJob, FailedChatJob

log = logging.getLogger(__name__)


class ChatProcessor:
    def __init__(self, sessions: SessionFactory, config: Settings) -> None:
        self.sessions, self.config = sessions, config

    async def generate(self, turn_id: str, attempt: int = 0) -> None:
        with self.sessions() as db:
            repository = ChatRepository(db)
            turn = repository.turn(turn_id)
            if turn is None:
                raise ApplicationError("Message no longer exists", non_retryable=True)
            if turn.status == "complete":
                return
            if turn.attempt != attempt:
                raise ApplicationError("This reply was replaced by a newer attempt", non_retryable=True)
            thread = repository.thread(turn.thread_id)
            if thread is None or thread.active_turn_id != turn_id:
                raise ApplicationError("This reply is no longer active", non_retryable=True)
            book = repository.book(thread.book_id)
            if book is None:
                raise ApplicationError("Book no longer exists", non_retryable=True)
            history: list[JsonValue] = []
            for item in repository.turns(thread.id):
                if item.status == "complete" and item.created_at < turn.created_at:
                    history.append({"question": item.question, "answer": item.answer})
            history = history[-6:]
            if not turn.sources and not self.config.knowledge_enabled:
                all_sources = passages(repository.readings(book.id))
                # Include recent questions for follow-ups such as 'Why did he do that?'.
                recent_questions = " ".join(
                    str(item["question"]) for item in history if isinstance(item, dict)
                )
                selected = select_context(all_sources, recent_questions + " " + turn.question)
                turn.sources = [source.model_dump(mode="json") for source in selected]
                turn.source_count = len(all_sources)
            sources = [SourcePassage.model_validate(item) for item in turn.sources]
            if not sources and not self.config.knowledge_enabled:
                raise ApplicationError(
                    "No extracted page text is available for this book", non_retryable=True
                )
            turn.status, turn.error = "generating", None
            question, title, language = turn.question, book.title, "en"
            scope, book_id = turn.scope, book.id
            UnitOfWork(db).commit()
        # No database session is held while loading models, querying Neo4j or calling an LLM.
        clarification: str | None = None
        if self.config.knowledge_enabled:
            from backend.app.knowledge.chunking import tokens
            from backend.app.knowledge.retrieval import retrieve

            while history and tokens(json.dumps(history)) > 2000:
                history.pop(0)
            if not sources:
                result = await retrieve(self.sessions, self.config, book_id, question, history, scope)
                sources, clarification = result.sources, result.clarification
                with self.sessions() as db:
                    turn = ChatRepository(db).turn(turn_id)
                    if turn is None or turn.attempt != attempt:
                        return
                    turn.sources = cast(list[JsonValue], [s.model_dump(mode="json") for s in sources])
                    turn.source_count = result.total
                    turn.retrieval = {
                        "strategy": result.plan.strategy,
                        "notes": cast(list[JsonValue], result.notes),
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "cost": result.cost,
                    }
                    db.commit()
        try:
            metrics: Metrics
            if clarification:
                answer = BookAnswer(answer=clarification, supported=False, citations=[])
                metrics = {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0}
            else:
                answer, metrics = await ai.answer_book(
                    question, sources, history, title, language, config=self.config
                )
        except (APIStatusError, ModelHTTPError) as exc:
            raise ApplicationError(
                f"The model provider rejected or could not complete this reply (HTTP {exc.status_code}). Check model settings before retrying.",
                non_retryable=exc.status_code in {400, 401, 402, 403, 404, 413, 422},
            ) from None
        except ConfigurationError:
            raise ApplicationError(
                "Configure the model provider before asking questions", non_retryable=True
            ) from None
        except UnexpectedModelBehavior as exc:
            log.warning("Chat output validation failed for turn %s: %s", turn_id, str(exc)[:500])
            raise ApplicationError(
                f"The model response did not pass output validation: {str(exc)[:400]}"
            ) from None
        except ModelAPIError:
            raise ApplicationError(
                "The model provider could not be reached or timed out. The saved question will be retried."
            ) from None
        with self.sessions() as db:
            repository = ChatRepository(db)
            turn = repository.turn(turn_id)
            if turn is None or turn.status == "complete" or turn.attempt != attempt:
                return
            turn.answer, turn.status, turn.error = answer.model_dump(mode="json"), "complete", None
            turn.model = self.config.deepinfra_model
            turn.input_tokens = metrics["input_tokens"] + int(str(turn.retrieval.get("input_tokens", 0)))
            turn.output_tokens = metrics["output_tokens"] + int(str(turn.retrieval.get("output_tokens", 0)))
            turn.estimated_cost = metrics["estimated_cost"] + float(str(turn.retrieval.get("cost", 0)))
            repository.release(turn.thread_id, turn_id)
            UnitOfWork(db).commit()

    def fail(self, turn_id: str, message: str, attempt: int = 0) -> None:
        with self.sessions() as db:
            repository = ChatRepository(db)
            turn = repository.turn(turn_id)
            if turn is not None and turn.status != "complete" and turn.attempt == attempt:
                turn.status, turn.error = "failed", message[:600]
                repository.release(turn.thread_id, turn_id)
                UnitOfWork(db).commit()

    @activity.defn(name="answer_book_chat")
    async def answer_activity(self, job: ChatJob) -> None:
        try:
            await with_heartbeats(self.generate(job["turn_id"], job["attempt"]))
        except (APIStatusError, ModelHTTPError) as exc:
            raise ApplicationError(
                f"The model provider rejected retrieval planning (HTTP {exc.status_code}). Check model settings.",
                non_retryable=exc.status_code in {400, 401, 402, 403, 404, 413, 422},
            ) from None

    @activity.defn(name="fail_book_chat")
    async def fail_activity(self, job: FailedChatJob) -> None:
        self.fail(job["turn_id"], job["message"], job["attempt"])
