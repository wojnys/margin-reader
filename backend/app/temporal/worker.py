from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from backend.app.core.config import settings
from backend.app.db.session import create_database
from backend.app.modules.chat.processing import ChatProcessor
from backend.app.modules.readings.processing import ReadingProcessor
from backend.app.temporal.activities import ReadingActivities
from backend.app.temporal.chat_workflow import AnswerBookChat
from backend.app.temporal.workflows import CreateConversation, ReadSpread


async def main() -> None:
    config = settings()
    activities = ReadingActivities(ReadingProcessor(create_database(config.database_url), config))
    chat = ChatProcessor(activities.processor.sessions, config)
    client = await Client.connect(config.temporal_address, namespace=config.temporal_namespace)
    logging.info("Reading worker connected; waiting for photographs")
    async with Worker(
        client,
        task_queue=config.temporal_task_queue,
        workflows=[ReadSpread, CreateConversation, AnswerBookChat],
        activities=[
            activities.extract_pages,
            activities.translate_pages,
            activities.create_learning,
            activities.finish_reading,
            activities.fail_reading,
            activities.create_conversation,
            activities.fail_conversation,
            chat.answer_activity,
            chat.fail_activity,
        ],
        max_concurrent_activities=2,
    ):
        await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
