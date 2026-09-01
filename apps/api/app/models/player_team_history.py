from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.player import Player
    from app.models.team import Team


class PlayerTeamHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "player_team_history"
    __table_args__ = (
        Index("ix_player_team_history_player_id_is_current", "player_id", "is_current"),
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
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    player: Mapped[Player] = relationship("Player", back_populates="team_history")
    team: Mapped[Team] = relationship("Team", back_populates="player_history")
