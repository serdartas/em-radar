"""add code_connection_id to team_profile

Revision ID: e1f2a3b4c5d6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.add_column(sa.Column("code_connection_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_team_profile_code_connection",
            "source_connection",
            ["code_connection_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.drop_constraint("fk_team_profile_code_connection", type_="foreignkey")
        batch_op.drop_column("code_connection_id")
