from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.player_metric_scoped_snapshot import PlayerMetricScopedSnapshot
    from app.models.player_metric_snapshot import PlayerMetricSnapshot


class MetricVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "metric_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_metric_versions_name_version"),
        Index("ix_metric_versions_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="RESEARCH",
        server_default="RESEARCH",
    )
    training_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    training_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    feature_names: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    standardization_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model_coefficients: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    regularization_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    shrinkage_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reference_population: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    snapshots: Mapped[list[PlayerMetricSnapshot]] = relationship(
        "PlayerMetricSnapshot",
        back_populates="metric_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    scoped_snapshots: Mapped[list[PlayerMetricScopedSnapshot]] = relationship(
        "PlayerMetricScopedSnapshot",
        back_populates="metric_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
