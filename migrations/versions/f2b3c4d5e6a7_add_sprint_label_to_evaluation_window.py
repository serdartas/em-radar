"""add sprint_label to evaluation_window

Revision ID: f2b3c4d5e6a7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2b3c4d5e6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("evaluation_window") as batch_op:
        batch_op.add_column(sa.Column("sprint_label", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("evaluation_window") as batch_op:
        batch_op.drop_column("sprint_label")
