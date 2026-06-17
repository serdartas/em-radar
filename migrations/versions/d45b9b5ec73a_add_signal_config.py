"""add signal config

Revision ID: d45b9b5ec73a
Revises: 5aa998bb48f2
Create Date: 2026-06-11 22:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d45b9b5ec73a"
down_revision: Union[str, Sequence[str], None] = "5aa998bb48f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signal_config",
        sa.Column("signal_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "severity_override",
            sa.Enum("info", "warning", "critical", name="severity"),
            nullable=True,
        ),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id"),
    )


def downgrade() -> None:
    op.drop_table("signal_config")
