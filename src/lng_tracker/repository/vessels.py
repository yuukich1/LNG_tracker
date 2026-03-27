from datetime import datetime

from sqlalchemy import delete, func, select

from lng_tracker.database.connect import async_session_maker
from lng_tracker.database.models import VesselHistory, VesselState


class VesselRepository:


    async def get_active_vessels(self):
        async with async_session_maker() as session:
            stmt = select(VesselState).where(VesselState.is_active.is_(True))
            result = await session.execute(stmt)
            return result.scalars().all()

    async def count_entries_since(self, since: datetime) -> int:
        async with async_session_maker() as session:
            stmt = select(func.count(VesselHistory.id)).where(
                VesselHistory.event_type == "ENTRY",
                VesselHistory.dt >= since,
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def clear_tracking_data(self) -> None:
        async with async_session_maker() as session:
            await session.execute(delete(VesselState))
            await session.execute(delete(VesselHistory))
            await session.commit()

    async def get_history(self):
        async with async_session_maker() as session:
            stmt = select(VesselHistory).order_by(VesselHistory.dt.desc())
            result = await session.execute(stmt)
            records = result.scalars().all()
            return records
