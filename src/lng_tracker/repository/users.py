from lng_tracker.database.connect import async_session_maker
from lng_tracker.database.models import Users
from sqlalchemy import select

class UserRepository:

    async def get_allowed_users(self):
        async with async_session_maker() as session:
            stmt = select(Users).filter(Users.is_allowed == True)
            result = await session.execute(stmt)
            return result.scalars().all()