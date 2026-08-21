"""add custom_fields to work_item

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("work_item") as batch_op:
        batch_op.add_column(
            sa.Column(
                "custom_fields",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )
    with op.batch_alter_table("work_item") as batch_op:
        batch_op.alter_column("custom_fields", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("work_item") as batch_op:
        batch_op.drop_column("custom_fields")
