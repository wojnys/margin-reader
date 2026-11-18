"""Opt-in integration with the project's real, persistent Temporal service. No paid AI calls."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Replayer, Worker

from backend.app.temporal.workflows import ReadSpread


@pytest.mark.skipif(
    os.getenv("TEMPORAL_TESTS") != "1", reason="Set TEMPORAL_TESTS=1 with docker compose up -d"
)
@pytest.mark.parametrize(
    ("learning_only", "pipeline_version", "expected"),
    [
        (False, None, ["extract", "extract", "translate", "teach", "finish"]),
        (True, None, ["teach", "finish"]),
        (False, 2, ["extract", "extract", "teach", "finish"]),
        (True, 2, ["teach", "finish"]),
        (False, 3, ["extract", "extract", "teach", "conversation", "finish"]),
        (True, 3, ["teach", "conversation", "finish"]),
    ],
)
async def test_real_workflow_retries_activity_and_history_replays(
    learning_only, pipeline_version, expected
):
    client = await Client.connect("127.0.0.1:7323")
    seen = []

    @activity.defn(name="extract_pages")
    async def extract(job: dict):
        seen.append("extract")
        activity.heartbeat()
        if activity.info().attempt == 1:
            raise RuntimeError("Simulated provider timeout")

    @activity.defn(name="translate_pages")
    async def translate(job: dict):
        seen.append("translate")
        activity.heartbeat()

    @activity.defn(name="create_learning")
    async def teach(job: dict):
        seen.append("teach")
        activity.heartbeat()

    @activity.defn(name="create_conversation")
    async def conversation(job: dict):
        seen.append("conversation")
        activity.heartbeat()

    @activity.defn(name="finish_reading")
    async def finish(job: dict):
        seen.append("finish")

    queue = f"margin-test-{uuid4()}"
    async with Worker(
        client, task_queue=queue, workflows=[ReadSpread], activities=[extract, translate, teach, conversation, finish]
    ):
        job = {"session_id": "test", "revision": 1, "learning_only": learning_only}
        if pipeline_version:
            job["pipeline_version"] = pipeline_version
        handle = await client.start_workflow(
            ReadSpread.run,
            job,
            id=queue,
            task_queue=queue,
            execution_timeout=timedelta(seconds=45),
        )
        await asyncio.wait_for(handle.result(), 40)
        history = await handle.fetch_history()
    assert seen == expected
    await Replayer(workflows=[ReadSpread]).replay_workflow(history)
