import asyncio

import httpx
from loguru import logger
from sqlalchemy import select, update

from lng_tracker.core.config import settings
from lng_tracker.database.connect import async_session_maker
from lng_tracker.database.models import VesselHistory, VesselState
from lng_tracker.services.notifier import TelegramNotifier


class LNGMonitorEngine:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.api_url = "https://tankermap.com/api/vessels/live"

    async def scan(self):
        logger.info("Starting vessel scan")

        async with async_session_maker() as session:
            stmt = select(VesselState).where(VesselState.is_active == True)
            res = await session.execute(stmt)
            active_in_db = {v.mmsi: {"zone": v.zone, "name": v.name} for v in res.scalars()}
            logger.debug("Loaded active vessels from DB: {}", len(active_in_db))

            async with httpx.AsyncClient(timeout=30) as client:
                try:
                    resp = await client.get(self.api_url)
                    resp.raise_for_status()
                    vessels = resp.json()
                    logger.info("Fetched {} vessels from API", len(vessels))
                except Exception as exc:
                    logger.error("API fetch error: {}", exc)
                    return

            current_mmsis = {}
            entry_count = 0
            exit_count = 0

            for vessel in vessels:
                name = vessel.get("name", "")
                if "LNG" not in name.upper():
                    continue

                mmsi = str(vessel.get("mmsi"))
                lat, lon = vessel.get("latitude"), vessel.get("longitude")
                if lat is None or lon is None:
                    logger.debug("Skipping vessel {} due to missing coordinates", mmsi)
                    continue

                for zone_name, bounds in settings.MONITOR_ZONES.items():
                    if bounds[0] <= lat <= bounds[1] and bounds[2] <= lon <= bounds[3]:
                        current_mmsis[mmsi] = zone_name

                        if mmsi not in active_in_db or active_in_db[mmsi]["zone"] != zone_name:
                            logger.info(
                                "ENTRY detected | vessel={} | mmsi={} | zone={}",
                                name,
                                mmsi,
                                zone_name,
                            )
                            await self.notifier.send_vessel_alert(
                                vessel_name=name,
                                zone=zone_name,
                                mmsi=mmsi,
                            )

                            await session.merge(
                                VesselState(mmsi=mmsi, name=name, zone=zone_name, is_active=True)
                            )
                            session.add(
                                VesselHistory(
                                    mmsi=mmsi,
                                    name=name,
                                    zone=zone_name,
                                    event_type="ENTRY",
                                )
                            )
                            entry_count += 1
                        break

            for mmsi, vessel_data in active_in_db.items():
                if mmsi not in current_mmsis:
                    await session.execute(
                        update(VesselState)
                        .where(VesselState.mmsi == mmsi)
                        .values(is_active=False)
                    )
                    session.add(
                        VesselHistory(
                            mmsi=mmsi,
                            name=vessel_data["name"],
                            zone=vessel_data["zone"],
                            event_type="EXIT",
                        )
                    )
                    exit_count += 1
                    logger.info("EXIT detected | mmsi={} | zone={}", mmsi, vessel_data["zone"])

            await session.commit()
            logger.info(
                "Scan finished | active_now={} | entries={} | exits={}",
                len(current_mmsis),
                entry_count,
                exit_count,
            )

    async def run_forever(self):
        logger.info("Monitor engine started")
        while True:
            await self.scan()
            await asyncio.sleep(settings.scan_interval)
