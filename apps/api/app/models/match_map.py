from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.player_map_stats import PlayerMapStats
    from app.models.team import Team


class MatchMap(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "match_maps"
    __table_args__ = (
        UniqueConstraint("match_id", "map_number", name="uq_match_maps_match_id_map_number"),
    )

    match_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        index=True,
    )
    map_number: Mapped[int] = mapped_column(Integer)
    map_name: Mapped[str] = mapped_column(String(64))
    team_a_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    team_b_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winner_team_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rounds_played: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match: Mapped[Match] = relationship("Match", back_populates="maps")
    winner_team: Mapped[Team | None] = relationship(
        "Team",
        back_populates="maps_won",
        foreign_keys="MatchMap.winner_team_id",
    )
    player_stats: Mapped[list[PlayerMapStats]] = relationship(
        "PlayerMapStats",
        back_populates="match_map",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
