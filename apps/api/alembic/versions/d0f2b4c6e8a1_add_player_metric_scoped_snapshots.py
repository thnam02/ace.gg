"""add player metric scoped snapshots for event CIR

Revision ID: d0f2b4c6e8a1
Revises: c9e1a3b7d4f2
Create Date: 2026-09-05 01:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0f2b4c6e8a1"
down_revision: str | None = "c9e1a3b7d4f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "player_metric_scoped_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("metric_version_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=False),
        sa.Column("cir_percentile", sa.Float(), nullable=True),
        sa.Column("raw_cir", sa.Float(), nullable=True),
        sa.Column("shrunk_raw_cir", sa.Float(), nullable=True),
        sa.Column("combat_factor", sa.Float(), nullable=True),
        sa.Column("rounds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("maps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sample_weight", sa.Float(), nullable=True),
        sa.Column("sample_status", sa.String(length=32), nullable=True),
        sa.Column("reliability", sa.String(length=32), nullable=True),
        sa.Column("kpr", sa.Float(), nullable=True),
        sa.Column("dpr", sa.Float(), nullable=True),
        sa.Column("expected_kpr", sa.Float(), nullable=True),
        sa.Column("expected_dpr", sa.Float(), nullable=True),
        sa.Column("kpr_residual", sa.Float(), nullable=True),
        sa.Column("negative_dpr_residual", sa.Float(), nullable=True),
        sa.Column("acs", sa.Float(), nullable=True),
        sa.Column("adr", sa.Float(), nullable=True),
        sa.Column("kd", sa.Float(), nullable=True),
        sa.Column("hs_pct", sa.Float(), nullable=True),
        sa.Column("apr", sa.Float(), nullable=True),
        sa.Column("kast", sa.Float(), nullable=True),
        sa.Column("opening_frequency", sa.Float(), nullable=True),
        sa.Column("opening_efficiency", sa.Float(), nullable=True),
        sa.Column("fk_per_round", sa.Float(), nullable=True),
        sa.Column("fd_per_round", sa.Float(), nullable=True),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("clutch", sa.Float(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("tier", sa.String(length=32), nullable=True),
        sa.Column("primary_agent", sa.String(length=64), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["metric_version_id"],
            ["metric_versions.id"],
            name=op.f("fk_player_metric_scoped_snapshots_metric_version_id_metric_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_metric_scoped_snapshots_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "metric_version_id",
            "player_id",
            "scope_type",
            "scope_id",
            name="uq_player_metric_scoped_snapshots_version_player_scope",
        ),
    )
    op.create_index(
        op.f("ix_player_metric_scoped_snapshots_metric_version_id"),
        "player_metric_scoped_snapshots",
        ["metric_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_player_metric_scoped_snapshots_player_id"),
        "player_metric_scoped_snapshots",
        ["player_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_player_metric_scoped_snapshots_scope_type"),
        "player_metric_scoped_snapshots",
        ["scope_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_player_metric_scoped_snapshots_scope_id"),
        "player_metric_scoped_snapshots",
        ["scope_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_metric_scoped_snapshots_scope_cir",
        "player_metric_scoped_snapshots",
        ["metric_version_id", "scope_type", "scope_id", "cir_percentile"],
        unique=False,
    )
    op.create_index(
        "ix_player_metric_scoped_snapshots_scope_rounds",
        "player_metric_scoped_snapshots",
        ["metric_version_id", "scope_type", "scope_id", "rounds"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_metric_scoped_snapshots_scope_rounds",
        table_name="player_metric_scoped_snapshots",
    )
    op.drop_index(
        "ix_player_metric_scoped_snapshots_scope_cir",
        table_name="player_metric_scoped_snapshots",
    )
    op.drop_index(
        op.f("ix_player_metric_scoped_snapshots_scope_id"),
        table_name="player_metric_scoped_snapshots",
    )
    op.drop_index(
        op.f("ix_player_metric_scoped_snapshots_scope_type"),
        table_name="player_metric_scoped_snapshots",
    )
    op.drop_index(
        op.f("ix_player_metric_scoped_snapshots_player_id"),
        table_name="player_metric_scoped_snapshots",
    )
    op.drop_index(
        op.f("ix_player_metric_scoped_snapshots_metric_version_id"),
        table_name="player_metric_scoped_snapshots",
    )
    op.drop_table("player_metric_scoped_snapshots")
