from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from lng_tracker.core.config import settings
from lng_tracker.database.base import Base


async_engine = create_async_engine(settings.database_url)

async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)