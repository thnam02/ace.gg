"""add event circuit/stage and data sync runs

Revision ID: c9e1a3b7d4f2
Revises: b8d4f2a0c1e3
Create Date: 2026-09-03 03:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9e1a3b7d4f2"
down_revision: str | None = "b8d4f2a0c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("circuit", sa.String(length=32), nullable=True))
    op.add_column("events", sa.Column("stage", sa.String(length=32), nullable=True))
    op.create_index("ix_events_circuit", "events", ["circuit"])
    op.create_table(
        "data_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("circuit", sa.String(length=32), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_sync_runs_circuit", "data_sync_runs", ["circuit"])
    op.create_index("ix_data_sync_runs_season_year", "data_sync_runs", ["season_year"])


def downgrade() -> None:
    op.drop_index("ix_data_sync_runs_season_year", table_name="data_sync_runs")
    op.drop_index("ix_data_sync_runs_circuit", table_name="data_sync_runs")
    op.drop_table("data_sync_runs")
    op.drop_index("ix_events_circuit", table_name="events")
    op.drop_column("events", "stage")
    op.drop_column("events", "circuit")
