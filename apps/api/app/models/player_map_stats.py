from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.match_map import MatchMap
    from app.models.player import Player
    from app.models.team import Team


class PlayerMapStats(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "player_map_stats"
    __table_args__ = (
        UniqueConstraint(
            "match_map_id",
            "player_id",
            name="uq_player_map_stats_match_map_id_player_id",
        ),
    )

    match_map_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("match_maps.id", ondelete="CASCADE"),
        index=True,
    )
    player_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="RESTRICT"),
        index=True,
    )
    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        index=True,
    )
    agent_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="RESTRICT"),
        index=True,
    )
    rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    first_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    first_deaths: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    adr: Mapped[float | None] = mapped_column(Float, nullable=True)
    kast_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    clutch_wins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clutch_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acs: Mapped[float | None] = mapped_column(Float, nullable=True)
    vlr_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    headshot_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_kills: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match_map: Mapped[MatchMap] = relationship("MatchMap", back_populates="player_stats")
    player: Mapped[Player] = relationship("Player", back_populates="map_stats")
    team: Mapped[Team] = relationship("Team", back_populates="map_stats")
    agent: Mapped[Agent] = relationship("Agent", back_populates="map_stats")
