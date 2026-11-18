from __future__ import annotations

from datetime import timedelta
from typing import TypedDict

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError


class IndexQueueState(TypedDict):
    active_job: str | None
    pending_jobs: list[str]
    processed: int
    failed_jobs: list[str]


@workflow.defn
class IndexBook:
    """Serialize a book's indexing batch, then close instead of waiting forever."""

    def __init__(self) -> None:
        self.pending: list[str] = []
        self.active_job: str | None = None
        self.processed = 0
        self.failed_jobs: list[str] = []
        self.finite = False

    @workflow.signal
    def enqueue(self, job_id: str) -> None:
        if job_id not in self.pending and (not self.finite or job_id != self.active_job):
            self.pending.append(job_id)

    @workflow.query
    def state(self) -> IndexQueueState:
        return {
            "active_job": self.active_job,
            "pending_jobs": list(self.pending),
            "processed": self.processed,
            "failed_jobs": list(self.failed_jobs),
        }

    @workflow.run
    async def run(
        self, pending: list[str], idle_seconds: float = 30, failed_jobs: list[str] | None = None
    ) -> dict[str, int]:
        # Replay pre-fix histories using their original indefinite wait/commands.
        self.finite = workflow.patched("knowledge-finite-batch-v1")
        self.failed_jobs = list(failed_jobs or [])
        self.pending = list(dict.fromkeys([*pending, *self.pending]))
        count = 0
        while True:
            if self.finite:
                try:
                    await workflow.wait_condition(
                        lambda: bool(self.pending), timeout=timedelta(seconds=max(0.1, min(idle_seconds, 60)))
                    )
                except TimeoutError:
                    # A signal racing completion causes Temporal to replay this
                    # workflow task; the queued item is not silently discarded.
                    if self.pending:
                        continue
                    if self.failed_jobs:
                        raise ApplicationError(
                            f"Book indexing finished with {len(self.failed_jobs)} failed jobs. See indexing errors in the application.",
                            type="BookIndexingFailed",
                            non_retryable=True,
                        )
                    return {"processed": self.processed, "failed": 0}
            else:
                await workflow.wait_condition(lambda: bool(self.pending))
            job_id = self.pending.pop(0)
            self.active_job = job_id
            try:
                await workflow.execute_activity(
                    "index_reading",
                    job_id,
                    start_to_close_timeout=timedelta(minutes=20),
                    schedule_to_close_timeout=timedelta(minutes=45),
                    heartbeat_timeout=timedelta(seconds=45),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except ActivityError as exc:
                message = (
                    exc.cause.message
                    if isinstance(exc.cause, ApplicationError)
                    else "Indexing failed after retries. Check the knowledge worker."
                )
                if self.finite:
                    await workflow.execute_activity(
                        "fail_indexing",
                        {"id": job_id, "message": message},
                        start_to_close_timeout=timedelta(seconds=30),
                        schedule_to_close_timeout=timedelta(minutes=2),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )
                    if job_id not in self.failed_jobs:
                        self.failed_jobs.append(job_id)
                else:
                    await workflow.execute_activity(
                        "fail_indexing",
                        {"id": job_id, "message": message},
                        start_to_close_timeout=timedelta(seconds=30),
                    )
            else:
                if self.finite and job_id in self.failed_jobs:
                    self.failed_jobs.remove(job_id)
            self.active_job = None
            self.processed += 1
            count += 1
            if count >= 25:
                if self.finite:
                    workflow.continue_as_new(args=[self.pending, idle_seconds, self.failed_jobs])
                else:
                    workflow.continue_as_new(self.pending)
