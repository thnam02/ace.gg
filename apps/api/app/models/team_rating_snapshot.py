from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.team import Team


class TeamRatingSnapshot(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "team_rating_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "match_id",
            name="uq_team_rating_snapshots_team_id_match_id",
        ),
    )

    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
    )
    match_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        index=True,
    )
    opponent_team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        index=True,
    )
    rating_before: Mapped[float] = mapped_column(Float, nullable=False)
    rating_after: Mapped[float] = mapped_column(Float, nullable=False)
    opponent_rating_before: Mapped[float] = mapped_column(Float, nullable=False)
    expected_win_probability: Mapped[float] = mapped_column(Float, nullable=False)
    result: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    team: Mapped[Team] = relationship(
        "Team",
        back_populates="rating_snapshots",
        foreign_keys=[team_id],
    )
    opponent_team: Mapped[Team] = relationship(
        "Team",
        back_populates="opponent_rating_snapshots",
        foreign_keys=[opponent_team_id],
    )
    match: Mapped[Match] = relationship("Match", back_populates="rating_snapshots")
