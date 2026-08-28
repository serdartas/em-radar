"""add team_gitlab_member and team_gitlab_repository; drop member_user_keys (M9-04)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_gitlab_member",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_profile_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("gitlab_user_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["source_connection.id"]),
        sa.ForeignKeyConstraint(["team_profile_id"], ["team_profile.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_profile_id", "gitlab_user_id"),
    )
    op.create_table(
        "team_gitlab_repository",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_profile_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("gitlab_project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("path_with_namespace", sa.String(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["source_connection.id"]),
        sa.ForeignKeyConstraint(["team_profile_id"], ["team_profile.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_profile_id", "gitlab_project_id"),
    )
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.drop_column("member_user_keys")


def downgrade() -> None:
    op.drop_table("team_gitlab_repository")
    op.drop_table("team_gitlab_member")
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.add_column(
            sa.Column("member_user_keys", sa.JSON(), nullable=False, server_default="[]")
        )
