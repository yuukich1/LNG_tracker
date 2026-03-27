import json
import math
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Any

from loguru import logger
from sqlalchemy import select

from lng_tracker.database.connect import async_session_maker
from lng_tracker.database.models import AISObservation, VesselHistory

LOCAL_TZ = datetime.now().astimezone().tzinfo or timezone.utc


def _to_iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _normalize_zone(zone: str | None) -> str | None:
    if not zone:
        return None
    return zone.strip().lower().replace(" ", "_")


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _avg(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _min_or_none(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    return min(filtered) if filtered else None


def _max_or_none(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    return max(filtered) if filtered else None


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_nm = 3440.065
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * earth_radius_nm * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _coerce_utc_naive(value: datetime, reference_dt: datetime | None = None) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    utc_candidate = value
    local_candidate = value.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    if reference_dt and utc_candidate > reference_dt + timedelta(minutes=30):
        return local_candidate
    if utc_candidate > now_utc + timedelta(minutes=5):
        return local_candidate
    return utc_candidate


@dataclass
class VesselZoneEvent:
    mmsi: int | None
    imo: int | None
    vessel_id: int | None
    name: str | None
    flag: str | None
    vessel_type: str | None
    deadweight: float | None
    zone: str
    entry_datetime: str
    exit_datetime: str | None
    duration_seconds: int
    duration_hours: float
    observations_count: int
    status: str
    avg_speed_knots: float | None
    min_speed_knots: float | None
    max_speed_knots: float | None
    avg_draught_meters: float | None
    min_draught_meters: float | None
    max_draught_meters: float | None
    draught_change_meters: float | None
    avg_cog_degrees: float | None
    start_latitude: float | None
    start_longitude: float | None
    end_latitude: float | None
    end_longitude: float | None
    centroid_latitude: float | None
    centroid_longitude: float | None
    position_source: str | None


class DatasetBuilder:
    def __init__(self, dataset_name: str = "lng_tracker_dataset"):
        self.dataset_name = dataset_name

    async def export(self, output_dir: str) -> dict[str, Any]:
        observations = await self._load_observations()
        history_records = await self._load_history()

        ais_rows = self._build_ais_rows(observations)
        zone_events = self._build_zone_events(observations, history_records)
        sts_candidates = self._build_sts_candidates(zone_events, observations)

        payload = {
            "dataset_name": self.dataset_name,
            "generated_at": _to_iso_utc(datetime.now(timezone.utc)),
            "format": "json",
            "ais_observations": ais_rows,
            "vessel_zone_events": zone_events,
            "sts_candidates": sts_candidates,
        }

        os.makedirs(output_dir, exist_ok=True)
        bundle_path = os.path.join(output_dir, f"{self.dataset_name}.json")
        self._write_json(bundle_path, payload)
        self._write_jsonl(
            os.path.join(output_dir, "ais_observations.jsonl"),
            ais_rows,
        )
        self._write_jsonl(
            os.path.join(output_dir, "vessel_zone_events.jsonl"),
            zone_events,
        )
        self._write_jsonl(
            os.path.join(output_dir, "sts_candidates.jsonl"),
            sts_candidates,
        )

        logger.info(
            "ML dataset exported | observations={} | zone_events={} | sts_candidates={} | dir={}",
            len(ais_rows),
            len(zone_events),
            len(sts_candidates),
            output_dir,
        )
        return payload

    async def _load_observations(self) -> list[AISObservation]:
        async with async_session_maker() as session:
            stmt = select(AISObservation).order_by(
                AISObservation.observed_at.asc(),
                AISObservation.id.asc(),
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def _load_history(self) -> list[VesselHistory]:
        async with async_session_maker() as session:
            stmt = select(VesselHistory).order_by(VesselHistory.dt.asc(), VesselHistory.id.asc())
            result = await session.execute(stmt)
            return result.scalars().all()

    def _build_ais_rows(self, observations: list[AISObservation]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for obs in observations:
            observed_at = _to_iso_utc(obs.observed_at)
            rows.append(
                {
                    "observed_at": observed_at,
                    "vessel_id": obs.vessel_id,
                    "name": obs.name,
                    "imo": obs.imo,
                    "mmsi": _safe_int(obs.mmsi),
                    "flag": obs.flag,
                    "vessel_type": obs.vessel_type,
                    "deadweight": obs.deadweight,
                    "latitude": obs.latitude,
                    "longitude": obs.longitude,
                    "speed_knots": obs.speed_knots,
                    "cog_degrees": obs.cog_degrees,
                    "draught_meters": obs.draught_meters,
                    "nav_status": obs.nav_status,
                    "destination": obs.destination,
                    "position_source": obs.position_source,
                    "zone": _normalize_zone(obs.zone),
                    "date_utc": observed_at[:10] if observed_at else None,
                    "hour_utc": obs.observed_at.hour if obs.observed_at else None,
                    "is_destination_missing": not bool(obs.destination and obs.destination.strip()),
                    "is_speed_missing": obs.speed_knots is None,
                    "is_draught_missing": obs.draught_meters is None,
                }
            )
        return rows

    def _build_zone_events(
        self,
        observations: list[AISObservation],
        history_records: list[VesselHistory],
    ) -> list[dict[str, Any]]:
        observations_by_vessel_zone: dict[tuple[str, str], list[AISObservation]] = defaultdict(list)
        for obs in observations:
            if obs.mmsi and obs.zone:
                observations_by_vessel_zone[(obs.mmsi, obs.zone)].append(obs)

        open_entries: dict[tuple[str, str], VesselHistory] = {}
        zone_events: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for record in history_records:
            key = (record.mmsi, record.zone)
            if record.event_type == "ENTRY":
                open_entries[key] = record
                continue

            if record.event_type != "EXIT":
                continue

            entry_record = open_entries.pop(key, None)
            if entry_record is None:
                continue

            zone_events.append(
                self._build_zone_event_from_window(
                    observations_by_vessel_zone.get(key, []),
                    entry_record=entry_record,
                    exit_dt=record.dt,
                    status="completed",
                )
            )

        for key, entry_record in open_entries.items():
            zone_events.append(
                self._build_zone_event_from_window(
                    observations_by_vessel_zone.get(key, []),
                    entry_record=entry_record,
                    exit_dt=now,
                    status="active",
                    emit_exit_datetime=False,
                )
            )

        zone_events.sort(key=lambda row: row["entry_datetime"], reverse=True)
        return zone_events

    def _build_zone_event_from_window(
        self,
        observations: list[AISObservation],
        entry_record: VesselHistory,
        exit_dt: datetime,
        status: str,
        emit_exit_datetime: bool = True,
    ) -> dict[str, Any]:
        reference_dt = observations[-1].observed_at if observations else None
        entry_dt = _coerce_utc_naive(entry_record.dt, reference_dt=reference_dt)
        exit_dt_utc = _coerce_utc_naive(exit_dt, reference_dt=reference_dt)
        window_observations = [
            obs
            for obs in observations
            if obs.observed_at and entry_dt <= obs.observed_at <= exit_dt_utc
        ]
        window_observations.sort(key=lambda obs: obs.observed_at)

        first_obs = window_observations[0] if window_observations else None
        last_obs = window_observations[-1] if window_observations else None
        speed_values = [obs.speed_knots for obs in window_observations]
        draught_values = [obs.draught_meters for obs in window_observations]
        cog_values = [obs.cog_degrees for obs in window_observations]
        latitudes = [obs.latitude for obs in window_observations if obs.latitude is not None]
        longitudes = [obs.longitude for obs in window_observations if obs.longitude is not None]
        duration_seconds = max(0, int((exit_dt_utc - entry_dt).total_seconds()))

        meta_obs = first_obs or last_obs
        min_draught = _min_or_none(draught_values)
        max_draught = _max_or_none(draught_values)

        return asdict(
            VesselZoneEvent(
                mmsi=_safe_int(entry_record.mmsi),
                imo=meta_obs.imo if meta_obs else None,
                vessel_id=meta_obs.vessel_id if meta_obs else None,
                name=entry_record.name,
                flag=meta_obs.flag if meta_obs else None,
                vessel_type=meta_obs.vessel_type if meta_obs else None,
                deadweight=meta_obs.deadweight if meta_obs else None,
                zone=_normalize_zone(entry_record.zone) or "unknown_zone",
                entry_datetime=_to_iso_utc(entry_dt) or "",
                exit_datetime=_to_iso_utc(exit_dt_utc) if emit_exit_datetime else None,
                duration_seconds=duration_seconds,
                duration_hours=round(duration_seconds / 3600, 4),
                observations_count=len(window_observations),
                status=status,
                avg_speed_knots=_avg(speed_values),
                min_speed_knots=_min_or_none(speed_values),
                max_speed_knots=_max_or_none(speed_values),
                avg_draught_meters=_avg(draught_values),
                min_draught_meters=min_draught,
                max_draught_meters=max_draught,
                draught_change_meters=(
                    round(max_draught - min_draught, 4)
                    if min_draught is not None and max_draught is not None
                    else None
                ),
                avg_cog_degrees=_avg(cog_values),
                start_latitude=first_obs.latitude if first_obs else None,
                start_longitude=first_obs.longitude if first_obs else None,
                end_latitude=last_obs.latitude if last_obs else None,
                end_longitude=last_obs.longitude if last_obs else None,
                centroid_latitude=_avg(latitudes),
                centroid_longitude=_avg(longitudes),
                position_source=meta_obs.position_source if meta_obs else None,
            )
        )

    def _build_sts_candidates(
        self,
        zone_events: list[dict[str, Any]],
        observations: list[AISObservation],
    ) -> list[dict[str, Any]]:
        observations_by_vessel_zone: dict[tuple[str, str], list[AISObservation]] = defaultdict(list)
        for obs in observations:
            normalized_zone = _normalize_zone(obs.zone)
            if obs.mmsi and normalized_zone:
                observations_by_vessel_zone[(obs.mmsi, normalized_zone)].append(obs)

        events_by_zone: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in zone_events:
            events_by_zone[event["zone"]].append(event)

        candidates: list[dict[str, Any]] = []

        for zone, events in events_by_zone.items():
            for event_a, event_b in combinations(events, 2):
                overlap = self._calculate_overlap(event_a, event_b)
                if overlap is None:
                    continue

                overlap_start, overlap_end, overlap_seconds = overlap
                if overlap_seconds <= 0:
                    continue

                distances = self._pairwise_distances_for_overlap(
                    observations_by_vessel_zone.get((str(event_a["mmsi"]), zone), []),
                    observations_by_vessel_zone.get((str(event_b["mmsi"]), zone), []),
                    overlap_start,
                    overlap_end,
                )
                if not distances:
                    continue

                avg_distance = sum(distances) / len(distances)
                min_distance = min(distances)
                if min_distance > 1.0:
                    continue

                sts_score = self._score_sts_candidate(
                    overlap_seconds=overlap_seconds,
                    avg_distance_nm=avg_distance,
                    min_distance_nm=min_distance,
                    event_a=event_a,
                    event_b=event_b,
                )
                if sts_score < 0.35:
                    continue

                candidates.append(
                    {
                        "vessel_a_mmsi": event_a["mmsi"],
                        "vessel_b_mmsi": event_b["mmsi"],
                        "vessel_a_name": event_a["name"],
                        "vessel_b_name": event_b["name"],
                        "zone": zone,
                        "overlap_start": _to_iso_utc(overlap_start),
                        "overlap_end": _to_iso_utc(overlap_end),
                        "overlap_seconds": overlap_seconds,
                        "overlap_hours": round(overlap_seconds / 3600, 4),
                        "avg_distance_nm": round(avg_distance, 4),
                        "min_distance_nm": round(min_distance, 4),
                        "vessel_a_avg_speed": event_a["avg_speed_knots"],
                        "vessel_b_avg_speed": event_b["avg_speed_knots"],
                        "vessel_a_draught_change": event_a["draught_change_meters"],
                        "vessel_b_draught_change": event_b["draught_change_meters"],
                        "sts_score": round(sts_score, 4),
                    }
                )

        candidates.sort(key=lambda row: row["sts_score"], reverse=True)
        return candidates

    @staticmethod
    def _calculate_overlap(
        event_a: dict[str, Any],
        event_b: dict[str, Any],
    ) -> tuple[datetime, datetime, int] | None:
        start_a = datetime.fromisoformat(event_a["entry_datetime"].replace("Z", "+00:00")).replace(tzinfo=None)
        end_a_raw = event_a["exit_datetime"] or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        end_a = datetime.fromisoformat(end_a_raw.replace("Z", "+00:00")).replace(tzinfo=None)

        start_b = datetime.fromisoformat(event_b["entry_datetime"].replace("Z", "+00:00")).replace(tzinfo=None)
        end_b_raw = event_b["exit_datetime"] or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        end_b = datetime.fromisoformat(end_b_raw.replace("Z", "+00:00")).replace(tzinfo=None)

        overlap_start = max(start_a, start_b)
        overlap_end = min(end_a, end_b)
        overlap_seconds = int((overlap_end - overlap_start).total_seconds())
        if overlap_seconds <= 0:
            return None
        return overlap_start, overlap_end, overlap_seconds

    def _pairwise_distances_for_overlap(
        self,
        observations_a: list[AISObservation],
        observations_b: list[AISObservation],
        overlap_start: datetime,
        overlap_end: datetime,
    ) -> list[float]:
        overlap_a = [
            obs
            for obs in observations_a
            if obs.observed_at
            and overlap_start <= obs.observed_at <= overlap_end
            and obs.latitude is not None
            and obs.longitude is not None
        ]
        overlap_b = [
            obs
            for obs in observations_b
            if obs.observed_at
            and overlap_start <= obs.observed_at <= overlap_end
            and obs.latitude is not None
            and obs.longitude is not None
        ]
        if not overlap_a or not overlap_b:
            return []

        distances: list[float] = []
        for obs_a in overlap_a:
            best_match = min(
                overlap_b,
                key=lambda obs_b: abs((obs_b.observed_at - obs_a.observed_at).total_seconds()),
            )
            time_delta = abs((best_match.observed_at - obs_a.observed_at).total_seconds())
            if time_delta > 900:
                continue
            distances.append(
                _haversine_nm(
                    obs_a.latitude,
                    obs_a.longitude,
                    best_match.latitude,
                    best_match.longitude,
                )
            )
        return distances

    @staticmethod
    def _score_sts_candidate(
        overlap_seconds: int,
        avg_distance_nm: float,
        min_distance_nm: float,
        event_a: dict[str, Any],
        event_b: dict[str, Any],
    ) -> float:
        overlap_component = min(overlap_seconds / 14400, 1.0) * 0.4
        proximity_component = max(0.0, 1.0 - min(avg_distance_nm, 2.0) / 2.0) * 0.35
        min_distance_component = max(0.0, 1.0 - min(min_distance_nm, 1.0) / 1.0) * 0.15

        avg_speed_a = event_a.get("avg_speed_knots")
        avg_speed_b = event_b.get("avg_speed_knots")
        speed_bonus = 0.0
        if avg_speed_a is not None and avg_speed_b is not None:
            speed_bonus = max(0.0, 1.0 - (avg_speed_a + avg_speed_b) / 8.0) * 0.05

        draught_change_a = event_a.get("draught_change_meters") or 0.0
        draught_change_b = event_b.get("draught_change_meters") or 0.0
        draught_bonus = min((draught_change_a + draught_change_b) / 4.0, 1.0) * 0.05

        return overlap_component + proximity_component + min_distance_component + speed_bonus + draught_bonus

    @staticmethod
    def _write_json(file_path: str, payload: dict[str, Any]) -> None:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    @staticmethod
    def _write_jsonl(file_path: str, rows: list[dict[str, Any]]) -> None:
        with open(file_path, "w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
