"""add team rating snapshots

Revision ID: e5a9c3d2f1b0
Revises: d4f8a2b1c9e0
Create Date: 2026-09-02 17:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a9c3d2f1b0"
down_revision: str | None = "d4f8a2b1c9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team_rating_snapshots",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("opponent_team_id", sa.Uuid(), nullable=False),
        sa.Column("rating_before", sa.Float(), nullable=False),
        sa.Column("rating_after", sa.Float(), nullable=False),
        sa.Column("opponent_rating_before", sa.Float(), nullable=False),
        sa.Column("expected_win_probability", sa.Float(), nullable=False),
        sa.Column("result", sa.Integer(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_team_rating_snapshots_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opponent_team_id"],
            ["teams.id"],
            name=op.f("fk_team_rating_snapshots_opponent_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_rating_snapshots_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_rating_snapshots")),
        sa.UniqueConstraint(
            "team_id",
            "match_id",
            name=op.f("uq_team_rating_snapshots_team_id_match_id"),
        ),
    )
    op.create_index(
        op.f("ix_team_rating_snapshots_effective_at"),
        "team_rating_snapshots",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_rating_snapshots_match_id"),
        "team_rating_snapshots",
        ["match_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_rating_snapshots_opponent_team_id"),
        "team_rating_snapshots",
        ["opponent_team_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_rating_snapshots_team_id"),
        "team_rating_snapshots",
        ["team_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_team_rating_snapshots_team_id"), table_name="team_rating_snapshots")
    op.drop_index(
        op.f("ix_team_rating_snapshots_opponent_team_id"),
        table_name="team_rating_snapshots",
    )
    op.drop_index(op.f("ix_team_rating_snapshots_match_id"), table_name="team_rating_snapshots")
    op.drop_index(
        op.f("ix_team_rating_snapshots_effective_at"),
        table_name="team_rating_snapshots",
    )
    op.drop_table("team_rating_snapshots")
