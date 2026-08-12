"""drop signal_config table (M5-12: hardcoded signal stack removed)

Revision ID: f5a6b7c8d9e0
Revises: e7e4d6a25ded
Create Date: 2026-08-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e7e4d6a25ded"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("signal_config")


def downgrade() -> None:
    op.create_table(
        "signal_config",
        sa.Column("signal_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("severity_override", sa.String(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id"),
    )
