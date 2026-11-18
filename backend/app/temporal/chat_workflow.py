from datetime import timedelta
from typing import TypedDict

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError


class ChatJob(TypedDict):
    turn_id: str
    attempt: int


class FailedChatJob(ChatJob):
    message: str


@workflow.defn
class AnswerBookChat:
    @workflow.run
    async def run(self, job: ChatJob) -> None:
        try:
            await workflow.execute_activity(
                "answer_book_chat",
                job,
                start_to_close_timeout=timedelta(minutes=7),
                schedule_to_close_timeout=timedelta(minutes=20),
                heartbeat_timeout=timedelta(seconds=45),
                retry_policy=RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=5)),
            )
        except ActivityError as exc:
            cause = exc.cause
            message = cause.message if isinstance(cause, ApplicationError) else "Reply failed after retries"
            await workflow.execute_activity(
                "fail_book_chat",
                {**job, "message": message},
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
