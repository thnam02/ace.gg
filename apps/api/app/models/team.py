from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.match_map import MatchMap
    from app.models.player_map_stats import PlayerMapStats
    from app.models.player_team_history import PlayerTeamHistory
    from app.models.team_rating_snapshot import TeamRatingSnapshot


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"

    vlr_team_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    tag: Mapped[str] = mapped_column(String(16))
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)

    player_history: Mapped[list[PlayerTeamHistory]] = relationship(
        "PlayerTeamHistory",
        back_populates="team",
    )
    matches_as_a: Mapped[list[Match]] = relationship(
        "Match",
        back_populates="team_a",
        foreign_keys="Match.team_a_id",
    )
    matches_as_b: Mapped[list[Match]] = relationship(
        "Match",
        back_populates="team_b",
        foreign_keys="Match.team_b_id",
    )
    matches_won: Mapped[list[Match]] = relationship(
        "Match",
        back_populates="winner_team",
        foreign_keys="Match.winner_team_id",
    )
    maps_won: Mapped[list[MatchMap]] = relationship(
        "MatchMap",
        back_populates="winner_team",
        foreign_keys="MatchMap.winner_team_id",
    )
    map_stats: Mapped[list[PlayerMapStats]] = relationship(
        "PlayerMapStats",
        back_populates="team",
    )
    rating_snapshots: Mapped[list[TeamRatingSnapshot]] = relationship(
        "TeamRatingSnapshot",
        back_populates="team",
        foreign_keys="TeamRatingSnapshot.team_id",
    )
    opponent_rating_snapshots: Mapped[list[TeamRatingSnapshot]] = relationship(
        "TeamRatingSnapshot",
        back_populates="opponent_team",
        foreign_keys="TeamRatingSnapshot.opponent_team_id",
    )
