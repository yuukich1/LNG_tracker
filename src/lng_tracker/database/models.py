from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from lng_tracker.database.base import Base

class VesselState(Base):

    __tablename__ = "vessel_states"

    mmsi: Mapped[str] = mapped_column( primary_key=True)
    name: Mapped[str] = mapped_column()
    zone: Mapped[str] = mapped_column()
    is_active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

class VesselHistory(Base):

    __tablename__ = "vessel_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mmsi: Mapped[str] = mapped_column()
    name: Mapped[str] = mapped_column()
    zone: Mapped[str] = mapped_column()
    event_type: Mapped[str] = mapped_column()  
    draught: Mapped[float] = mapped_column(nullable=True)
    dt: Mapped[datetime] = mapped_column(default=datetime.now)


class Users(Base):

    __tablename__ = "users"
    
    telegram_id: Mapped[int] = mapped_column(primary_key=True)
    is_allowed: Mapped[bool] = mapped_column(default=False)
    username: Mapped[str] = mapped_column(nullable=True)