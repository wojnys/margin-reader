from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from temporalio import activity

from backend.app.modules.conversation.processing import ConversationProcessor
from backend.app.modules.readings.processing import ReadingProcessor
from backend.app.temporal.workflows import FailedJob, ReadingJob


async def with_heartbeats(awaitable: Awaitable[None]) -> None:
    async def beat() -> None:
        while True:
            activity.heartbeat()
            await asyncio.sleep(10)

    task = asyncio.create_task(beat())
    try:
        await awaitable
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class ReadingActivities:
    def __init__(self, processor: ReadingProcessor) -> None:
        self.processor = processor
        self.conversation = ConversationProcessor(processor.sessions, processor.config)

    @activity.defn(name="extract_pages")
    async def extract_pages(self, job: ReadingJob) -> None:
        await with_heartbeats(self.processor.process_stage(job, "extract"))

    @activity.defn(name="translate_pages")
    async def translate_pages(self, job: ReadingJob) -> None:
        await with_heartbeats(self.processor.process_stage(job, "translate"))

    @activity.defn(name="create_learning")
    async def create_learning(self, job: ReadingJob) -> None:
        await with_heartbeats(self.processor.process_stage(job, "teach"))

    @activity.defn(name="finish_reading")
    async def finish_reading(self, job: ReadingJob) -> None:
        self.processor.finish(job)

    @activity.defn(name="fail_reading")
    async def fail_reading(self, job: FailedJob) -> None:
        self.processor.fail(job)

    @activity.defn(name="create_conversation")
    async def create_conversation(self, job: ReadingJob) -> None:
        await with_heartbeats(self.conversation.generate(job))

    @activity.defn(name="fail_conversation")
    async def fail_conversation(self, job: FailedJob) -> None:
        self.conversation.fail(job)
