from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from backend.app.core.config import Settings
from backend.app.core.runtime import Runtime
from backend.app.db.session import UnitOfWork
from backend.app.modules.chat.repository import ChatRepository
from backend.app.modules.conversation.repository import ConversationRepository
from backend.app.modules.knowledge.repository import KnowledgeRepository
from backend.app.modules.readings.repository import ReadingRepository
from backend.app.temporal.workflows import ReadingJob

log = logging.getLogger(__name__)


async def connect_temporal(config: Settings) -> Client:
    return await asyncio.wait_for(
        Client.connect(config.temporal_address, namespace=config.temporal_namespace), 4
    )


async def dispatch_pending(runtime: Runtime) -> None:
    while True:
        try:
            with runtime.sessions() as db:
                jobs = [
                    (
                        ReadingJob(
                            session_id=s.id,
                            revision=s.revision,
                            learning_only=bool(s.extraction),
                            pipeline_version=3,
                        ),
                        s.attempt,
                    )
                    for s in ReadingRepository(db).pending()
                ]
                conversation_jobs = [
                    (ReadingJob(session_id=item.session_id, revision=item.revision), item.attempt)
                    for item in ConversationRepository(db).pending()
                ]
                chat_jobs = [(item.id, item.attempt) for item in ChatRepository(db).pending()]
                index_jobs = [(item.id, item.book_id) for item in KnowledgeRepository(db).pending()]
            if index_jobs:
                client = await connect_temporal(runtime.config)
                for job_id, book_id in index_jobs:
                    await client.start_workflow(
                        "IndexBook",
                        [],
                        id=f"knowledge-book-{book_id}",
                        task_queue=runtime.config.knowledge_task_queue,
                        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                        start_signal="enqueue",
                        start_signal_args=[job_id],
                        rpc_timeout=timedelta(seconds=5),
                    )
                    with runtime.sessions() as db:
                        item = KnowledgeRepository(db).job(job_id)
                        if item is not None and item.status == "pending":
                            item.status = "queued"
                            UnitOfWork(db).commit()
            if jobs:
                client = await connect_temporal(runtime.config)
                for job, attempt in jobs:
                    try:
                        await client.start_workflow(
                            "ReadSpread",
                            job,
                            id=f"spread-{job['session_id']}-v{job['revision']}-a{attempt}",
                            task_queue=runtime.config.temporal_task_queue,
                            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                            rpc_timeout=timedelta(seconds=5),
                        )
                    except WorkflowAlreadyStartedError:
                        pass
                    with runtime.sessions() as db:
                        ReadingRepository(db).mark_queued(job["session_id"], job["revision"])
                        UnitOfWork(db).commit()
            if conversation_jobs:
                client = await connect_temporal(runtime.config)
                for job, attempt in conversation_jobs:
                    try:
                        await client.start_workflow(
                            "CreateConversation",
                            job,
                            id=f"conversation-{job['session_id']}-v{job['revision']}-a{attempt}",
                            task_queue=runtime.config.temporal_task_queue,
                            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                            rpc_timeout=timedelta(seconds=5),
                        )
                    except WorkflowAlreadyStartedError:
                        pass
                    with runtime.sessions() as db:
                        ConversationRepository(db).mark_queued(job["session_id"], job["revision"], attempt)
                        UnitOfWork(db).commit()
            if chat_jobs:
                client = await connect_temporal(runtime.config)
                for turn_id, attempt in chat_jobs:
                    try:
                        await client.start_workflow(
                            "AnswerBookChat",
                            {"turn_id": turn_id, "attempt": attempt},
                            id=f"chat-{turn_id}-a{attempt}",
                            task_queue=runtime.config.temporal_task_queue,
                            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                            rpc_timeout=timedelta(seconds=5),
                        )
                    except WorkflowAlreadyStartedError:
                        pass
                    with runtime.sessions() as db:
                        ChatRepository(db).mark_queued(turn_id, attempt)
                        UnitOfWork(db).commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("Workflow service unavailable; saved uploads will be submitted again shortly")
        await asyncio.sleep(4)
