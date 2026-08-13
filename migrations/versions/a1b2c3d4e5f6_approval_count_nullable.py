"""make merge_request.approval_count nullable (M5-16: approval API sentinel)

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-08-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("merge_request") as batch_op:
        batch_op.alter_column("approval_count", nullable=True, existing_type=sa.Integer())


def downgrade() -> None:
    with op.batch_alter_table("merge_request") as batch_op:
        batch_op.alter_column(
            "approval_count",
            nullable=False,
            existing_type=sa.Integer(),
            server_default="0",
        )
