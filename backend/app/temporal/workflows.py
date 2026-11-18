from __future__ import annotations

from datetime import timedelta
from typing import NotRequired, TypedDict

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError


class ReadingJob(TypedDict):
    session_id: str
    revision: int
    learning_only: NotRequired[bool]
    pipeline_version: NotRequired[int]


class FailedJob(ReadingJob):
    message: str


@workflow.defn
class ReadSpread:
    @workflow.run
    async def run(self, job: ReadingJob) -> None:
        try:
            if job.get("pipeline_version") in {2, 3}:
                stages = (
                    ["create_learning", "finish_reading"]
                    if job.get("learning_only")
                    else ["extract_pages", "create_learning", "finish_reading"]
                )
            else:
                # Preserve the recorded command sequence of in-flight v1 workflow histories.
                stages = (
                    ["create_learning", "finish_reading"]
                    if job.get("learning_only")
                    else ["extract_pages", "translate_pages", "create_learning", "finish_reading"]
                )
            for name in stages:
                if name == "finish_reading" and job.get("pipeline_version") == 3:
                    await create_conversation(job)
                await workflow.execute_activity(
                    name,
                    job,
                    start_to_close_timeout=timedelta(minutes=7),
                    schedule_to_close_timeout=timedelta(minutes=25),
                    heartbeat_timeout=timedelta(seconds=45) if name != "finish_reading" else None,
                    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=5), maximum_attempts=3),
                )
        except ActivityError as exc:
            cause = exc.cause
            message = (
                cause.message
                if isinstance(cause, ApplicationError)
                else "Processing stopped after retries. Check the worker and try again."
            )
            await workflow.execute_activity(
                "fail_reading", {**job, "message": message}, start_to_close_timeout=timedelta(seconds=30)
            )
            raise


async def create_conversation(job: ReadingJob) -> None:
    """Optional enrichment fails independently of the original reading material."""
    try:
        await workflow.execute_activity(
            "create_conversation",
            job,
            start_to_close_timeout=timedelta(minutes=7),
            schedule_to_close_timeout=timedelta(minutes=25),
            heartbeat_timeout=timedelta(seconds=45),
            retry_policy=RetryPolicy(initial_interval=timedelta(seconds=5), maximum_attempts=3),
        )
    except ActivityError as exc:
        cause = exc.cause
        message = (
            cause.message
            if isinstance(cause, ApplicationError)
            else "Conversation generation stopped after retries"
        )
        await workflow.execute_activity(
            "fail_conversation",
            {**job, "message": message},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )


@workflow.defn
class CreateConversation:
    @workflow.run
    async def run(self, job: ReadingJob) -> None:
        await create_conversation(job)
