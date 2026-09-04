from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.metric_version import MetricVersion
    from app.models.player import Player


class PlayerMetricScopedSnapshot(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Persisted CIR + descriptive stats for a non-global observation window.

    Event scope changes which maps are included. It does not change frozen
    CIR v0.2 model parameters (expectations, μ/σ, k, reference CDF).
    """

    __tablename__ = "player_metric_scoped_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "metric_version_id",
            "player_id",
            "scope_type",
            "scope_id",
            name="uq_player_metric_scoped_snapshots_version_player_scope",
        ),
        Index(
            "ix_player_metric_scoped_snapshots_scope_cir",
            "metric_version_id",
            "scope_type",
            "scope_id",
            "cir_percentile",
        ),
        Index(
            "ix_player_metric_scoped_snapshots_scope_rounds",
            "metric_version_id",
            "scope_type",
            "scope_id",
            "rounds",
        ),
    )

    metric_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("metric_versions.id", ondelete="CASCADE"),
        index=True,
    )
    player_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    cir_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_cir: Mapped[float | None] = mapped_column(Float, nullable=True)
    shrunk_raw_cir: Mapped[float | None] = mapped_column(Float, nullable=True)
    combat_factor: Mapped[float | None] = mapped_column(Float, nullable=True)

    rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    maps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sample_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reliability: Mapped[str | None] = mapped_column(String(32), nullable=True)

    kpr: Mapped[float | None] = mapped_column(Float, nullable=True)
    dpr: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_kpr: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_dpr: Mapped[float | None] = mapped_column(Float, nullable=True)
    kpr_residual: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_dpr_residual: Mapped[float | None] = mapped_column(Float, nullable=True)

    acs: Mapped[float | None] = mapped_column(Float, nullable=True)
    adr: Mapped[float | None] = mapped_column(Float, nullable=True)
    kd: Mapped[float | None] = mapped_column(Float, nullable=True)
    hs_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    apr: Mapped[float | None] = mapped_column(Float, nullable=True)
    kast: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    fk_per_round: Mapped[float | None] = mapped_column(Float, nullable=True)
    fd_per_round: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    clutch: Mapped[float | None] = mapped_column(Float, nullable=True)

    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    primary_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)

    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    player: Mapped[Player] = relationship("Player", back_populates="scoped_metric_snapshots")
    metric_version: Mapped[MetricVersion] = relationship(
        "MetricVersion",
        back_populates="scoped_snapshots",
    )
