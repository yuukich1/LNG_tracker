from sqlalchemy import select, update

from lng_tracker.database.connect import async_session_maker
from lng_tracker.database.models import Users


class UserRepository:

    
    async def get_allowed_users(self):
        async with async_session_maker() as session:
            stmt = select(Users).where(Users.is_allowed.is_(True))
            result = await session.execute(stmt)
            return result.scalars().all()

    async def save_user(self, telegram_id: int, username: str | None, is_allowed: bool = False):
        async with async_session_maker() as session:
            user = Users(
                telegram_id=telegram_id,
                username=username,
                is_allowed=is_allowed,
            )
            await session.merge(user)
            await session.commit()
            return user

    async def get_by_telegram_id(self, telegram_id: int):
        async with async_session_maker() as session:
            stmt = select(Users).where(Users.telegram_id == telegram_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def approve_user(self, telegram_id: int) -> None:
        async with async_session_maker() as session:
            await session.execute(
                update(Users)
                .where(Users.telegram_id == telegram_id)
                .values(is_allowed=True)
            )
            await session.commit()
