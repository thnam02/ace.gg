from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.match_map import MatchMap
    from app.models.team import Team


class Match(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "matches"

    vlr_match_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("events.id", ondelete="RESTRICT"),
        index=True,
    )
    team_a_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        index=True,
    )
    team_b_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        index=True,
    )
    winner_team_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    best_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="matches")
    team_a: Mapped[Team] = relationship(
        "Team",
        back_populates="matches_as_a",
        foreign_keys="Match.team_a_id",
    )
    team_b: Mapped[Team] = relationship(
        "Team",
        back_populates="matches_as_b",
        foreign_keys="Match.team_b_id",
    )
    winner_team: Mapped[Team | None] = relationship(
        "Team",
        back_populates="matches_won",
        foreign_keys="Match.winner_team_id",
    )
    maps: Mapped[list[MatchMap]] = relationship(
        "MatchMap",
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
