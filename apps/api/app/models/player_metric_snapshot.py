from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.metric_version import MetricVersion
    from app.models.player import Player


class PlayerMetricSnapshot(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "player_metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "metric_version_id",
            name="uq_player_metric_snapshots_player_id_metric_version_id",
        ),
        Index(
            "ix_player_metric_snapshots_metric_version_id_cir",
            "metric_version_id",
            "cir",
        ),
        Index(
            "ix_player_metric_snapshots_metric_version_id_sample_status",
            "metric_version_id",
            "sample_status",
        ),
    )

    player_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        index=True,
    )
    metric_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("metric_versions.id", ondelete="CASCADE"),
        index=True,
    )
    raw_cir: Mapped[float | None] = mapped_column(Float, nullable=True)
    shrunk_raw_cir: Mapped[float | None] = mapped_column(Float, nullable=True)
    cir: Mapped[float | None] = mapped_column(Float, nullable=True)
    combat_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    team_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    clutch_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    maps_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    events_played: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    sample_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reliability: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    player: Mapped[Player] = relationship("Player", back_populates="metric_snapshots")
    metric_version: Mapped[MetricVersion] = relationship(
        "MetricVersion",
        back_populates="snapshots",
    )
