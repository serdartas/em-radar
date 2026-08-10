"""add unique constraint comment source external_id

Revision ID: e7e4d6a25ded
Revises: e1f2a3b4c5d6
Create Date: 2026-08-10 22:01:53.210818

"""

from typing import Sequence, Union

from alembic import op


revision: str = "e7e4d6a25ded"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("comment") as batch_op:
        batch_op.create_unique_constraint(
            "uq_comment_source_external_id", ["source", "external_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("comment") as batch_op:
        batch_op.drop_constraint("uq_comment_source_external_id", type_="unique")
