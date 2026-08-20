"""add report_job table (M8.3-02: async report jobs)

Revision ID: a3b4c5d6e7f8
Revises: c3d4e5f6a7b8
Create Date: 2026-08-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_profile_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("report_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("window_type", sa.String(), nullable=True),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["team_profile_id"], ["team_profile.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("report_job")
