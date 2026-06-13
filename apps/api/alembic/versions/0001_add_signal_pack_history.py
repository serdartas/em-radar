"""add signal_pack_history

Revision ID: 0001
Revises:
Create Date: 2026-06-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_pack_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pack_name", sa.String(), nullable=False),
        sa.Column("raw_yaml", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("signal_pack_history")
