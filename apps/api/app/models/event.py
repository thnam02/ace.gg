from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.match import Match


class Event(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "events"

    vlr_event_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    season_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    matches: Mapped[list[Match]] = relationship("Match", back_populates="event")
