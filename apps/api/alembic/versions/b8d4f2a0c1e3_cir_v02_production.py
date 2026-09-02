"""add CIR v0.2 production status and snapshot ranking fields

Revision ID: b8d4f2a0c1e3
Revises: f6b2c4d8e1a0
Create Date: 2026-09-03 02:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8d4f2a0c1e3"
down_revision: str | None = "f6b2c4d8e1a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "metric_versions",
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="RESEARCH",
            nullable=False,
        ),
    )
    op.create_index("ix_metric_versions_status", "metric_versions", ["status"], unique=False)
    op.add_column(
        "player_metric_snapshots",
        sa.Column("events_played", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("player_metric_snapshots", sa.Column("sample_weight", sa.Float(), nullable=True))
    op.add_column(
        "player_metric_snapshots",
        sa.Column("sample_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "player_metric_snapshots",
        sa.Column("reliability", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "player_metric_snapshots",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "player_metric_snapshots",
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_player_metric_snapshots_metric_version_id_cir",
        "player_metric_snapshots",
        ["metric_version_id", "cir"],
        unique=False,
    )
    op.create_index(
        "ix_player_metric_snapshots_metric_version_id_sample_status",
        "player_metric_snapshots",
        ["metric_version_id", "sample_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_metric_snapshots_metric_version_id_sample_status",
        table_name="player_metric_snapshots",
    )
    op.drop_index(
        "ix_player_metric_snapshots_metric_version_id_cir",
        table_name="player_metric_snapshots",
    )
    op.drop_column("player_metric_snapshots", "calculated_at")
    op.drop_column("player_metric_snapshots", "details")
    op.drop_column("player_metric_snapshots", "reliability")
    op.drop_column("player_metric_snapshots", "sample_status")
    op.drop_column("player_metric_snapshots", "sample_weight")
    op.drop_column("player_metric_snapshots", "events_played")
    op.drop_index("ix_metric_versions_status", table_name="metric_versions")
    op.drop_column("metric_versions", "status")
