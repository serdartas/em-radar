"""rename gitlab_user_id/gitlab_project_id to provider_user_id/provider_project_id (M9-17)

Revision ID: f3a4b5c6d7e8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-28 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: add the new column as nullable so the backfill UPDATE can populate it before
    # NOT NULL is enforced.  Using nullable here avoids a server_default="" that would
    # otherwise linger on the column after recreation.
    with op.batch_alter_table("team_gitlab_member") as batch_op:
        batch_op.add_column(sa.Column("provider_user_id", sa.String(), nullable=True))

    # Step 2: copy the integer values as strings.
    op.execute("UPDATE team_gitlab_member SET provider_user_id = CAST(gitlab_user_id AS TEXT)")

    # Step 3: recreate the table without the old column, enforcing NOT NULL on the new column
    # and adding the new unique constraint.  recreate="always" forces SQLite to drop+recreate
    # so the original unnamed unique constraint is naturally removed.
    with op.batch_alter_table("team_gitlab_member", recreate="always") as batch_op:
        batch_op.drop_column("gitlab_user_id")
        batch_op.alter_column("provider_user_id", nullable=False, existing_type=sa.String())
        batch_op.create_unique_constraint(
            "uq_team_gitlab_member_team_profile_id_provider_user_id",
            ["team_profile_id", "provider_user_id"],
        )

    # Same for team_gitlab_repository.
    with op.batch_alter_table("team_gitlab_repository") as batch_op:
        batch_op.add_column(sa.Column("provider_project_id", sa.String(), nullable=True))

    op.execute(
        "UPDATE team_gitlab_repository SET provider_project_id = CAST(gitlab_project_id AS TEXT)"
    )

    with op.batch_alter_table("team_gitlab_repository", recreate="always") as batch_op:
        batch_op.drop_column("gitlab_project_id")
        batch_op.alter_column("provider_project_id", nullable=False, existing_type=sa.String())
        batch_op.create_unique_constraint(
            "uq_team_gitlab_repository_team_profile_id_provider_project_id",
            ["team_profile_id", "provider_project_id"],
        )


def downgrade() -> None:
    # WARNING: downgrade is lossy for any non-numeric provider_user_id / provider_project_id
    # (e.g. GitHub node IDs).  SQLite CAST of a non-numeric string to INTEGER returns 0,
    # which would silently corrupt multiple rows into the same id and may violate the
    # restored unique constraint.  Only downgrade when all stored ids are numeric.
    with op.batch_alter_table("team_gitlab_member") as batch_op:
        batch_op.add_column(sa.Column("gitlab_user_id", sa.Integer(), nullable=True))

    op.execute("UPDATE team_gitlab_member SET gitlab_user_id = CAST(provider_user_id AS INTEGER)")

    with op.batch_alter_table("team_gitlab_member", recreate="always") as batch_op:
        batch_op.drop_column("provider_user_id")
        batch_op.alter_column("gitlab_user_id", nullable=False, existing_type=sa.Integer())
        batch_op.create_unique_constraint(
            "uq_team_gitlab_member_team_profile_id_gitlab_user_id",
            ["team_profile_id", "gitlab_user_id"],
        )

    with op.batch_alter_table("team_gitlab_repository") as batch_op:
        batch_op.add_column(sa.Column("gitlab_project_id", sa.Integer(), nullable=True))

    op.execute(
        "UPDATE team_gitlab_repository SET gitlab_project_id = CAST(provider_project_id AS INTEGER)"
    )

    with op.batch_alter_table("team_gitlab_repository", recreate="always") as batch_op:
        batch_op.drop_column("provider_project_id")
        batch_op.alter_column("gitlab_project_id", nullable=False, existing_type=sa.Integer())
        batch_op.create_unique_constraint(
            "uq_team_gitlab_repository_team_profile_id_gitlab_project_id",
            ["team_profile_id", "gitlab_project_id"],
        )
