"""add team signal_config_group_ids

Revision ID: b7e2c1a9d4f3
Revises: 2a8c3d7e9f1b
Create Date: 2026-06-22 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e2c1a9d4f3"
down_revision: Union[str, Sequence[str], None] = "2a8c3d7e9f1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("team_profile", sa.Column("signal_config_group_ids", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE team_profile SET signal_config_group_ids = '[]' "
        "WHERE signal_config_group_ids IS NULL"
    )
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.alter_column("signal_config_group_ids", nullable=False)


def downgrade() -> None:
    op.drop_column("team_profile", "signal_config_group_ids")
