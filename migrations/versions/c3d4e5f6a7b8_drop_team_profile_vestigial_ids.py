"""drop team_profile project_ids board_ids repository_ids

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.drop_column("project_ids")
        batch_op.drop_column("board_ids")
        batch_op.drop_column("repository_ids")


def downgrade() -> None:
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.add_column(
            sa.Column("repository_ids", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(sa.Column("board_ids", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(
            sa.Column("project_ids", sa.JSON(), nullable=False, server_default="[]")
        )
