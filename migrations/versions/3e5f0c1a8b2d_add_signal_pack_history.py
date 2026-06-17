"""add signal_pack_history

Revision ID: 3e5f0c1a8b2d
Revises: d45b9b5ec73a
Create Date: 2026-06-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3e5f0c1a8b2d"
down_revision: Union[str, Sequence[str], None] = "d45b9b5ec73a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
