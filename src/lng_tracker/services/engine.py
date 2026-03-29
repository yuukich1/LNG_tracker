import asyncio
from datetime import datetime, timezone

import httpx
from loguru import logger
from sqlalchemy import insert, select, update

from lng_tracker.core.config import settings
from lng_tracker.database.connect import async_session_maker
from lng_tracker.database.models import AISObservation, VesselHistory, VesselState
from lng_tracker.services.notifier import TelegramNotifier


class LNGMonitorEngine:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.api_url = "https://tankermap.com/api/vessels/live"

    async def scan(self):
        logger.info("Starting vessel scan")
        async with async_session_maker() as session:
            stmt = select(VesselState.mmsi, VesselState.zone, VesselState.name).where(
                VesselState.is_active.is_(True)
            )
            res = await session.execute(stmt)
            active_in_db = {
                mmsi: {"zone": zone, "name": name}
                for mmsi, zone, name in res.all()
            }
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
            observed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            ais_rows = []
            history_rows = []

            for vessel in vessels:
                name = vessel.get("name", "")
                if "LNG" not in name.upper():
                    continue

                mmsi = str(vessel.get("mmsi"))
                lat = self._safe_float(vessel.get("latitude"))
                lon = self._safe_float(vessel.get("longitude"))
                if lat is None or lon is None:
                    logger.debug("Skipping vessel {} due to missing coordinates", mmsi)
                    continue

                matched_zone_name = None
                for zone_name, bounds in settings.MONITOR_ZONES.items():
                    if bounds[0] <= lat <= bounds[1] and bounds[2] <= lon <= bounds[3]:
                        matched_zone_name = zone_name
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
                                VesselState(
                                    mmsi=mmsi,
                                    name=name,
                                    zone=zone_name,
                                    is_active=True,
                                )
                            )

                            history_rows.append(
                                {
                                    "mmsi": mmsi,
                                    "name": name,
                                    "zone": zone_name,
                                    "event_type": "ENTRY",
                                    "draught": self._safe_float(vessel.get("draught")),
                                }
                            )
                            entry_count += 1
                        break

                ais_rows.append(
                    {
                        "observed_at": observed_at,
                        "vessel_id": self._safe_int(vessel.get("id")),
                        "name": name or None,
                        "imo": self._safe_int(vessel.get("imo")),
                        "mmsi": mmsi,
                        "flag": vessel.get("flag"),
                        "vessel_type": vessel.get("vessel_type") or vessel.get("type"),
                        "deadweight": self._safe_float(vessel.get("deadweight")),
                        "latitude": lat,
                        "longitude": lon,
                        "speed_knots": self._safe_float(vessel.get("speed")),
                        "cog_degrees": self._safe_float(vessel.get("course")),
                        "draught_meters": self._safe_float(vessel.get("draught")),
                        "nav_status": vessel.get("nav_status"),
                        "destination": vessel.get("destination"),
                        "position_source": vessel.get("position_source") or "tankermap_live_api",
                        "zone": matched_zone_name,
                    }
                )

            for mmsi, vessel_data in active_in_db.items():
                if mmsi not in current_mmsis:
                    await session.execute(
                        update(VesselState)
                        .where(VesselState.mmsi == mmsi)
                        .values(is_active=False)
                    )
                    history_rows.append(
                        {
                            "mmsi": mmsi,
                            "name": vessel_data["name"],
                            "zone": vessel_data["zone"],
                            "event_type": "EXIT",
                        }
                    )
                    exit_count += 1
                    logger.info("EXIT detected | mmsi={} | zone={}", mmsi, vessel_data["zone"])

            if ais_rows:
                await session.execute(insert(AISObservation), ais_rows)
            if history_rows:
                await session.execute(insert(VesselHistory), history_rows)

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

    @staticmethod
    def _safe_int(value):
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value):
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
