from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.player_map_stats import PlayerMapStats
    from app.models.player_team_history import PlayerTeamHistory


class Player(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "players"

    vlr_player_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    handle: Mapped[str] = mapped_column(String(128))
    real_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)

    team_history: Mapped[list[PlayerTeamHistory]] = relationship(
        "PlayerTeamHistory",
        back_populates="player",
    )
    map_stats: Mapped[list[PlayerMapStats]] = relationship(
        "PlayerMapStats",
        back_populates="player",
    )
