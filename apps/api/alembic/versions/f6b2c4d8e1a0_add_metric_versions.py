"""add metric versions and player metric snapshots

Revision ID: f6b2c4d8e1a0
Revises: e5a9c3d2f1b0
Create Date: 2026-09-02 17:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6b2c4d8e1a0"
down_revision: str | None = "e5a9c3d2f1b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metric_versions",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("training_start", sa.Date(), nullable=True),
        sa.Column("training_end", sa.Date(), nullable=True),
        sa.Column("feature_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "standardization_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("model_coefficients", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "regularization_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("shrinkage_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reference_population", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_versions")),
        sa.UniqueConstraint("name", "version", name=op.f("uq_metric_versions_name_version")),
    )
    op.create_table(
        "player_metric_snapshots",
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("metric_version_id", sa.Uuid(), nullable=False),
        sa.Column("raw_cir", sa.Float(), nullable=True),
        sa.Column("shrunk_raw_cir", sa.Float(), nullable=True),
        sa.Column("cir", sa.Float(), nullable=True),
        sa.Column("combat_component", sa.Float(), nullable=True),
        sa.Column("opening_component", sa.Float(), nullable=True),
        sa.Column("team_component", sa.Float(), nullable=True),
        sa.Column("clutch_component", sa.Float(), nullable=True),
        sa.Column("rounds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("maps_played", sa.Integer(), server_default="0", nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["metric_version_id"],
            ["metric_versions.id"],
            name=op.f("fk_player_metric_snapshots_metric_version_id_metric_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_metric_snapshots_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_metric_snapshots")),
        sa.UniqueConstraint(
            "player_id",
            "metric_version_id",
            name=op.f("uq_player_metric_snapshots_player_id_metric_version_id"),
        ),
    )
    op.create_index(
        op.f("ix_player_metric_snapshots_metric_version_id"),
        "player_metric_snapshots",
        ["metric_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_player_metric_snapshots_player_id"),
        "player_metric_snapshots",
        ["player_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_player_metric_snapshots_player_id"),
        table_name="player_metric_snapshots",
    )
    op.drop_index(
        op.f("ix_player_metric_snapshots_metric_version_id"),
        table_name="player_metric_snapshots",
    )
    op.drop_table("player_metric_snapshots")
    op.drop_table("metric_versions")
