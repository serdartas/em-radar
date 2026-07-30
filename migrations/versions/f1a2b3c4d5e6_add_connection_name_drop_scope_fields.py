"""add connection name and drop scope fields

Revision ID: f1a2b3c4d5e6
Revises: c9d1e2f3a4b5
Create Date: 2026-07-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "c9d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_source_connection = sa.table(
    "source_connection",
    sa.column("id", sa.String()),
    sa.column("connector_name", sa.String()),
    sa.column("name", sa.String()),
    sa.column("created_at", sa.DateTime()),
)


def upgrade() -> None:
    op.add_column("source_connection", sa.Column("name", sa.String(), nullable=True))
    _backfill_names()
    with op.batch_alter_table("source_connection") as batch_op:
        batch_op.alter_column("name", nullable=False)
        batch_op.create_unique_constraint("uq_source_connection_name", ["name"])
        batch_op.drop_column("selected_project_ids")
        batch_op.drop_column("selected_board_ids")
        batch_op.drop_column("selected_repository_ids")


def _backfill_names() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(_source_connection.c.id, _source_connection.c.connector_name).order_by(
            _source_connection.c.created_at
        )
    ).all()
    used_names: set[str] = set()
    for row_id, connector_name in rows:
        base = f"{connector_name} connection"
        candidate = base
        suffix = 2
        while candidate in used_names:
            candidate = f"{base} {suffix}"
            suffix += 1
        used_names.add(candidate)
        bind.execute(
            sa.update(_source_connection)
            .where(_source_connection.c.id == row_id)
            .values(name=candidate)
        )


def downgrade() -> None:
    with op.batch_alter_table("source_connection") as batch_op:
        batch_op.drop_constraint("uq_source_connection_name", type_="unique")
        batch_op.drop_column("name")
        batch_op.add_column(sa.Column("selected_project_ids", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("selected_board_ids", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("selected_repository_ids", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE source_connection SET selected_project_ids = '[]' WHERE selected_project_ids IS NULL"
    )
    op.execute(
        "UPDATE source_connection SET selected_board_ids = '[]' WHERE selected_board_ids IS NULL"
    )
    op.execute(
        "UPDATE source_connection SET selected_repository_ids = '[]'"
        " WHERE selected_repository_ids IS NULL"
    )
    with op.batch_alter_table("source_connection") as batch_op:
        batch_op.alter_column("selected_project_ids", nullable=False)
        batch_op.alter_column("selected_board_ids", nullable=False)
        batch_op.alter_column("selected_repository_ids", nullable=False)
