import asyncio
import os

from loguru import logger

from lng_tracker.database.connect import async_engine, init_db
from lng_tracker.services.dataset_builder import DatasetBuilder


async def main():
    os.makedirs("data/datasets", exist_ok=True)
    await init_db()
    builder = DatasetBuilder()
    await builder.export(os.path.join(os.getcwd(), "data", "datasets"))
    await async_engine.dispose()


if __name__ == "__main__":
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level="INFO", enqueue=False)
    asyncio.run(main())
