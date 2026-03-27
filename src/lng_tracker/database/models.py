from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column
from lng_tracker.database.base import Base


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class VesselState(Base):

    __tablename__ = "vessel_states"

    mmsi: Mapped[str] = mapped_column( primary_key=True)
    name: Mapped[str] = mapped_column()
    zone: Mapped[str] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow_naive, onupdate=utcnow_naive)

class VesselHistory(Base):

    __tablename__ = "vessel_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mmsi: Mapped[str] = mapped_column()
    name: Mapped[str] = mapped_column()
    zone: Mapped[str] = mapped_column()
    event_type: Mapped[str] = mapped_column()  
    draught: Mapped[float] = mapped_column(nullable=True)
    dt: Mapped[datetime] = mapped_column(default=utcnow_naive)


class AISObservation(Base):

    __tablename__ = "ais_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    observed_at: Mapped[datetime] = mapped_column(default=utcnow_naive, index=True)
    vessel_id: Mapped[int | None] = mapped_column(nullable=True)
    name: Mapped[str | None] = mapped_column(nullable=True)
    imo: Mapped[int | None] = mapped_column(nullable=True)
    mmsi: Mapped[str | None] = mapped_column(index=True, nullable=True)
    flag: Mapped[str | None] = mapped_column(nullable=True)
    vessel_type: Mapped[str | None] = mapped_column(nullable=True)
    deadweight: Mapped[float | None] = mapped_column(nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    speed_knots: Mapped[float | None] = mapped_column(nullable=True)
    cog_degrees: Mapped[float | None] = mapped_column(nullable=True)
    draught_meters: Mapped[float | None] = mapped_column(nullable=True)
    nav_status: Mapped[str | None] = mapped_column(nullable=True)
    destination: Mapped[str | None] = mapped_column(nullable=True)
    position_source: Mapped[str | None] = mapped_column(nullable=True)
    zone: Mapped[str | None] = mapped_column(nullable=True, index=True)


class Users(Base):

    __tablename__ = "users"
    
    telegram_id: Mapped[int] = mapped_column(primary_key=True)
    is_allowed: Mapped[bool] = mapped_column(default=False)
    username: Mapped[str] = mapped_column(nullable=True)
