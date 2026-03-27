import asyncio
import os

from aiogram import Bot, Dispatcher
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from lng_tracker.bot.handlers import router as bot_router
from lng_tracker.bot.middlewares import AccessMiddleware
from lng_tracker.core.config import settings
from lng_tracker.database.connect import async_engine, init_db
from lng_tracker.services.engine import LNGMonitorEngine
from lng_tracker.services.notifier import TelegramNotifier


async def main():
    if not os.path.exists("data"):
        os.makedirs("data")
        logger.info("Created data directory: data/")
    else:
        logger.debug("Data directory already exists: data/")

    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully")

    bot = Bot(token=settings.telegram_token)
    dp = Dispatcher()

    dp.message.outer_middleware(AccessMiddleware())
    dp.include_router(bot_router)
    notifier = TelegramNotifier(bot)
    engine = LNGMonitorEngine(notifier)
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(notifier.send_daily_csv_report, "cron", hour=23, minute=0)
    scheduler.start()
    logger.info(
        "Starting bot and monitor engine | scan_interval={}s | admin_chat_id={}",
        settings.scan_interval,
        settings.chat_id,
    )

    try:
        await asyncio.gather(dp.start_polling(bot), engine.run_forever())
    except Exception as exc:
        logger.exception("Critical application error: {}", exc)
    finally:
        logger.info("Shutting down application...")
        await bot.session.close()
        await async_engine.dispose()
        logger.info("Application stopped")


if __name__ == "__main__":
    logger.remove()
    logger.add(
        "data/debug.log",
        rotation="10 MB",
        level="INFO",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
    logger.add(lambda msg: print(msg, end=""), level="INFO", enqueue=True)

    logger.info("LNG Tracker is starting...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.warning("Process interrupted by user")
