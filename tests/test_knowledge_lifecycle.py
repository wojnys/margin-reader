"""Real Temporal lifecycle/replay tests with synthetic activities and no AI calls."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from temporalio import activity, workflow
from temporalio.client import Client, WorkflowFailureError
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner, Worker

from backend.app.temporal.knowledge_workflow import IndexBook

pytestmark = pytest.mark.skipif(
    os.environ.get("TEMPORAL_TESTS") != "1", reason="Opt-in local Temporal, synthetic activities only"
)


class Activities:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.finished: list[str] = []
        self.failures: list[str] = []
        self.holding = asyncio.Event()
        self.release = asyncio.Event()

    @activity.defn(name="index_reading")
    async def index(self, job_id: str) -> None:
        self.started.append(job_id)
        if job_id == "hold":
            self.holding.set()
            await self.release.wait()
        if job_id.startswith("bad") and self.started.count(job_id) == 1:
            raise ApplicationError("Synthetic invalid output", non_retryable=True)
        self.finished.append(job_id)

    @activity.defn(name="fail_indexing")
    async def fail(self, payload: dict[str, str]) -> None:
        self.failures.append(payload["id"])


async def test_signal_queue_deduplicates_active_job_closes_and_reopens_after_success() -> None:
    client = await Client.connect("127.0.0.1:7323")
    queue = "finite-index-test-" + str(uuid4())
    activities = Activities()
    async with Worker(
        client, task_queue=queue, workflows=[IndexBook], activities=[activities.index, activities.fail]
    ):
        first = await client.start_workflow(
            "IndexBook",
            args=[[], 0.2],
            id=queue,
            task_queue=queue,
            start_signal="enqueue",
            start_signal_args=["hold"],
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            execution_timeout=timedelta(seconds=30),
        )
        await asyncio.wait_for(activities.holding.wait(), 10)
        await first.signal("enqueue", "hold")
        await first.signal("enqueue", "second")
        state = await first.query(IndexBook.state)
        assert state["active_job"] == "hold" and state["pending_jobs"] == ["second"]
        activities.release.set()
        assert (await asyncio.wait_for(first.result(), 15))["processed"] == 2
        first_description = await first.describe()
        first_history = await first.fetch_history()
        second = await client.start_workflow(
            "IndexBook",
            args=[[], 0.2],
            id=queue,
            task_queue=queue,
            start_signal="enqueue",
            start_signal_args=["third"],
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            execution_timeout=timedelta(seconds=30),
        )
        assert (await asyncio.wait_for(second.result(), 15))["processed"] == 1
        second_description = await second.describe()
        assert second_description.run_id != first_description.run_id
        assert activities.started == ["hold", "second", "third"]
        second_history = await second.fetch_history()
    replayer = Replayer(workflows=[IndexBook])
    await replayer.replay_workflow(first_history)
    await replayer.replay_workflow(second_history)


async def test_failed_job_does_not_abandon_next_job_and_batch_ends_failed() -> None:
    client = await Client.connect("127.0.0.1:7323")
    queue = "failed-index-test-" + str(uuid4())
    activities = Activities()
    async with Worker(
        client, task_queue=queue, workflows=[IndexBook], activities=[activities.index, activities.fail]
    ):
        handle = await client.start_workflow(
            IndexBook.run,
            args=[["bad", "good"], 0.2],
            id=queue,
            task_queue=queue,
            execution_timeout=timedelta(seconds=30),
        )
        with pytest.raises(WorkflowFailureError) as caught:
            await asyncio.wait_for(handle.result(), 15)
        assert isinstance(caught.value.cause, ApplicationError)
        assert caught.value.cause.type == "BookIndexingFailed"
        assert activities.started == ["bad", "good"]
        assert activities.finished == ["good"] and activities.failures == ["bad"]
        assert (await handle.describe()).status.name == "FAILED"
        history = await handle.fetch_history()
        failure_activity = next(
            e.activity_task_scheduled_event_attributes
            for e in history.events
            if e.HasField("activity_task_scheduled_event_attributes")
            and e.activity_task_scheduled_event_attributes.activity_type.name == "fail_indexing"
        )
        # Temporal may clamp this to the enclosing run's shorter test deadline.
        assert 0 < failure_activity.schedule_to_close_timeout.seconds <= 120
        assert failure_activity.retry_policy.maximum_attempts == 3
        fresh = await client.start_workflow(
            "IndexBook",
            args=[["later"], 0.2],
            id=queue,
            task_queue=queue,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
        )
        assert (await asyncio.wait_for(fresh.result(), 15))["processed"] == 1
    await Replayer(workflows=[IndexBook]).replay_workflow(history)


async def test_continue_as_new_preserves_pending_jobs_and_failure_outcome() -> None:
    client = await Client.connect("127.0.0.1:7323")
    queue = "continued-index-test-" + str(uuid4())
    activities = Activities()
    jobs = ["bad-first", *[f"job-{i}" for i in range(26)]]
    async with Worker(
        client, task_queue=queue, workflows=[IndexBook], activities=[activities.index, activities.fail]
    ):
        handle = await client.start_workflow(
            IndexBook.run,
            args=[jobs, 0.2],
            id=queue,
            task_queue=queue,
            execution_timeout=timedelta(seconds=45),
        )
        with pytest.raises(WorkflowFailureError) as caught:
            await asyncio.wait_for(handle.result(), 30)
        assert (
            isinstance(caught.value.cause, ApplicationError)
            and caught.value.cause.type == "BookIndexingFailed"
        )
        assert activities.started == jobs
        assert len(activities.finished) == 26


async def test_successful_retry_during_idle_clears_previous_failure() -> None:
    client = await Client.connect("127.0.0.1:7323")
    queue = "retried-index-test-" + str(uuid4())
    activities = Activities()
    async with Worker(
        client, task_queue=queue, workflows=[IndexBook], activities=[activities.index, activities.fail]
    ):
        handle = await client.start_workflow(
            IndexBook.run,
            args=[["bad-once"], 1.0],
            id=queue,
            task_queue=queue,
            execution_timeout=timedelta(seconds=30),
        )
        for _ in range(100):
            state = await handle.query(IndexBook.state)
            if state["failed_jobs"]:
                break
            await asyncio.sleep(0.05)
        assert state["failed_jobs"] == ["bad-once"]
        await handle.signal("enqueue", "bad-once")
        assert await asyncio.wait_for(handle.result(), 15) == {"processed": 2, "failed": 0}
        assert activities.finished == ["bad-once"]
        assert (await handle.describe()).status.name == "COMPLETED"
        history = await handle.fetch_history()
    await Replayer(workflows=[IndexBook]).replay_workflow(history)


@workflow.defn(name="IndexBook")
class LegacyIndexBook:
    """Generate a pre-patch history without private book data."""

    def __init__(self) -> None:
        self.pending: list[str] = []

    @workflow.signal
    def enqueue(self, job_id: str) -> None:
        if job_id not in self.pending:
            self.pending.append(job_id)

    @workflow.run
    async def run(self, pending: list[str]) -> None:
        self.pending = list(dict.fromkeys([*pending, *self.pending]))
        while True:
            await workflow.wait_condition(lambda: bool(self.pending))
            job_id = self.pending.pop(0)
            from temporalio.common import RetryPolicy

            await workflow.execute_activity(
                "index_reading",
                job_id,
                start_to_close_timeout=timedelta(minutes=20),
                schedule_to_close_timeout=timedelta(minutes=45),
                heartbeat_timeout=timedelta(seconds=45),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )


async def test_pre_patch_history_replays_without_nondeterminism() -> None:
    client = await Client.connect("127.0.0.1:7323")
    queue = "legacy-index-test-" + str(uuid4())
    activities = Activities()
    async with Worker(
        client,
        task_queue=queue,
        workflows=[LegacyIndexBook],
        activities=[activities.index],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await client.start_workflow(
            "IndexBook", ["hold"], id=queue, task_queue=queue, execution_timeout=timedelta(seconds=30)
        )
        await asyncio.wait_for(activities.holding.wait(), 10)
        activities.release.set()
        for _ in range(100):
            if activities.finished:
                break
            await asyncio.sleep(0.05)
        assert activities.finished == ["hold"]
        await handle.cancel()
        with pytest.raises(WorkflowFailureError):
            await handle.result()
        history = await handle.fetch_history()
    await Replayer(workflows=[IndexBook]).replay_workflow(history)
