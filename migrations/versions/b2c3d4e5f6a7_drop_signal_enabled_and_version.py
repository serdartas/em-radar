"""drop signal enabled and version

Revision ID: b2c3d4e5f6a7
Revises: f2b3c4d5e6a7
Create Date: 2026-08-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "f2b3c4d5e6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("signal_definition") as batch_op:
        batch_op.drop_column("enabled")
        batch_op.drop_column("version")


def downgrade() -> None:
    with op.batch_alter_table("signal_definition") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"))
