"""Compatibility entry point for the separated Temporal worker."""
import asyncio
from backend.app.temporal.worker import main
if __name__ == "__main__":
    asyncio.run(main())
