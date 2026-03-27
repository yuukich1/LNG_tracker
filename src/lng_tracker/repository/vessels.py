from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select

from lng_tracker.database.connect import async_session_maker
from lng_tracker.database.models import VesselHistory, VesselState


@dataclass
class VesselHistoryReportRow:
    name: str
    zone: str
    event_type: str
    dt: datetime
    time_in_zone: str


@dataclass
class VesselPassageRow:
    mmsi: str
    name: str
    zone: str
    entry_dt: datetime
    exit_dt: datetime | None
    duration_seconds: int
    duration_hms: str
    status: str


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
            return result.scalars().all()

    async def get_history_report_rows(self, since: datetime | None = None):
        records = await self._get_history_records_ascending(since=since)
        report_rows = self._build_history_report_rows(records) # type: ignore
        report_rows.sort(key=lambda row: row.dt, reverse=True)
        return report_rows

    async def get_training_dataset_rows(self):
        records = await self._get_history_records_ascending()
        passages = self._build_passage_rows(records) # type: ignore
        passages.sort(key=lambda row: row.entry_dt, reverse=True)
        return passages

    async def _get_history_records_ascending(self, since: datetime | None = None):
        async with async_session_maker() as session:
            stmt = select(VesselHistory).order_by(VesselHistory.dt.asc(), VesselHistory.id.asc())
            if since is not None:
                stmt = stmt.where(VesselHistory.dt >= since)
            result = await session.execute(stmt)
            return result.scalars().all()

    def _build_history_report_rows(self, records: list[VesselHistory]):
        open_entries: dict[tuple[str, str], VesselHistory] = {}
        report_rows: list[VesselHistoryReportRow] = []
        now = datetime.now()

        for record in records:
            key = (record.mmsi, record.zone)

            if record.event_type == "ENTRY":
                open_entries[key] = record
                report_rows.append(
                    VesselHistoryReportRow(
                        name=record.name,
                        zone=record.zone,
                        event_type=record.event_type,
                        dt=record.dt,
                        time_in_zone="",
                    )
                )
                continue

            if record.event_type == "EXIT":
                entry_record = open_entries.pop(key, None)
                name = entry_record.name if entry_record else record.name
                duration = record.dt - entry_record.dt if entry_record else None
                report_rows.append(
                    VesselHistoryReportRow(
                        name=name,
                        zone=record.zone,
                        event_type=record.event_type,
                        dt=record.dt,
                        time_in_zone=self._format_duration(duration.total_seconds()) if duration else "",
                    )
                )
                continue

            report_rows.append(
                VesselHistoryReportRow(
                    name=record.name,
                    zone=record.zone,
                    event_type=record.event_type,
                    dt=record.dt,
                    time_in_zone="",
                )
            )

        for entry_record in open_entries.values():
            for row in report_rows:
                if (
                    row.name == entry_record.name
                    and row.zone == entry_record.zone
                    and row.event_type == entry_record.event_type
                    and row.dt == entry_record.dt
                ):
                    row.time_in_zone = self._format_duration((now - entry_record.dt).total_seconds())
                    break

        return report_rows

    def _build_passage_rows(self, records: list[VesselHistory]):
        open_entries: dict[tuple[str, str], VesselHistory] = {}
        passages: list[VesselPassageRow] = []
        now = datetime.now()

        for record in records:
            key = (record.mmsi, record.zone)

            if record.event_type == "ENTRY":
                open_entries[key] = record
                continue

            if record.event_type != "EXIT":
                continue

            entry_record = open_entries.pop(key, None)
            if entry_record is None:
                continue

            duration_seconds = max(0, int((record.dt - entry_record.dt).total_seconds()))
            passages.append(
                VesselPassageRow(
                    mmsi=record.mmsi,
                    name=entry_record.name,
                    zone=record.zone,
                    entry_dt=entry_record.dt,
                    exit_dt=record.dt,
                    duration_seconds=duration_seconds,
                    duration_hms=self._format_duration(duration_seconds),
                    status="completed",
                )
            )

        for (mmsi, zone), entry_record in open_entries.items():
            duration_seconds = max(0, int((now - entry_record.dt).total_seconds()))
            passages.append(
                VesselPassageRow(
                    mmsi=mmsi,
                    name=entry_record.name,
                    zone=zone,
                    entry_dt=entry_record.dt,
                    exit_dt=None,
                    duration_seconds=duration_seconds,
                    duration_hms=self._format_duration(duration_seconds),
                    status="active",
                )
            )

        return passages

    @staticmethod
    def _format_duration(total_seconds: float | int) -> str:
        total_seconds = max(0, int(total_seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
