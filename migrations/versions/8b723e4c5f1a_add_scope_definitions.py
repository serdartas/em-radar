"""add scope definitions

Revision ID: 8b723e4c5f1a
Revises: 3e5f0c1a8b2d
Create Date: 2026-06-18 18:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b723e4c5f1a"
down_revision: Union[str, Sequence[str], None] = "3e5f0c1a8b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scope_definition",
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "scope_type",
            sa.Enum("project", "board", "repository", "saved_filter", "custom", name="scopetype"),
            nullable=False,
        ),
        sa.Column("external_ref", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["source_connection.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("team_profile", sa.Column("scope_ids", sa.JSON(), nullable=True))
    op.execute("UPDATE team_profile SET scope_ids = '[]' WHERE scope_ids IS NULL")
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.alter_column("scope_ids", nullable=False)


def downgrade() -> None:
    op.drop_column("team_profile", "scope_ids")
    op.drop_table("scope_definition")
