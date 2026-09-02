"""add event status column

Revision ID: d4f8a2b1c9e0
Revises: c2eda69cd4cf
Create Date: 2026-09-02 16:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f8a2b1c9e0"
down_revision: str | None = "c2eda69cd4cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "status")
