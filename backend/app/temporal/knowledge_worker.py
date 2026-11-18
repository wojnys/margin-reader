from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from backend.app.core.config import settings
from backend.app.db.session import create_database
from backend.app.modules.knowledge.processing import KnowledgeProcessor
from backend.app.temporal.knowledge_workflow import IndexBook


async def main() -> None:
    config = settings()
    processor = KnowledgeProcessor(create_database(config.database_url), config)
    client = await Client.connect(config.temporal_address, namespace=config.temporal_namespace)
    async with Worker(
        client,
        task_queue=config.knowledge_task_queue,
        workflows=[IndexBook],
        activities=[processor.index_activity, processor.fail_activity],
        max_concurrent_activities=2,
    ):
        await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
