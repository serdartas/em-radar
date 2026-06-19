"""add signal definitions

Revision ID: 1f4f7b6b6e4a
Revises: 8b723e4c5f1a
Create Date: 2026-06-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1f4f7b6b6e4a"
down_revision: Union[str, Sequence[str], None] = "8b723e4c5f1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signal_definition",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("target_scopes", sa.JSON(), nullable=False),
        sa.Column("expression", sa.JSON(), nullable=False),
        sa.Column("report_settings", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "origin",
            sa.Enum("system_template", "user_created", "imported", name="signalorigin"),
            nullable=False,
        ),
        sa.Column("template_key", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("signal_definition")
