"""add scope definitions

Revision ID: 8b723e4c5f1a
Revises: 3e5f0c1a8b2d
Create Date: 2026-06-18 18:40:00.000000

"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "8b723e4c5f1a"
down_revision: Union[str, Sequence[str], None] = "3e5f0c1a8b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_source_connection = sa.table(
    "source_connection",
    sa.column("id", sa.Uuid()),
    sa.column("connector_name", sa.String()),
    sa.column("selected_project_ids", sa.JSON()),
    sa.column("selected_board_ids", sa.JSON()),
)
_scope_definition = sa.table(
    "scope_definition",
    sa.column("connection_id", sa.Uuid()),
    sa.column("name", sa.String()),
    sa.column("scope_type", sa.String()),
    sa.column("external_ref", sa.JSON()),
    sa.column("capabilities", sa.JSON()),
    sa.column("id", sa.Uuid()),
    sa.column("created_at", sa.DateTime()),
    sa.column("updated_at", sa.DateTime()),
)
_team_profile = sa.table(
    "team_profile",
    sa.column("id", sa.Uuid()),
    sa.column("connection_ids", sa.JSON()),
    sa.column("scope_ids", sa.JSON()),
)


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
    _backfill_scope_definitions()
    with op.batch_alter_table("team_profile") as batch_op:
        batch_op.alter_column("scope_ids", nullable=False)


def downgrade() -> None:
    op.drop_column("team_profile", "scope_ids")
    op.drop_table("scope_definition")


def _backfill_scope_definitions() -> None:
    bind = op.get_bind()
    connection_scope_ids: dict[str, list[str]] = {}
    for connection in bind.execute(sa.select(_source_connection)).mappings():
        if connection["connector_name"] != "jira":
            continue
        created_scope_ids = _create_legacy_scopes(
            bind,
            connection_id=connection["id"],
            selected_project_ids=_json_list(connection["selected_project_ids"]),
            selected_board_ids=_json_list(connection["selected_board_ids"]),
        )
        if created_scope_ids:
            connection_scope_ids[str(connection["id"])] = created_scope_ids

    if not connection_scope_ids:
        return

    for team in bind.execute(sa.select(_team_profile)).mappings():
        existing_scope_ids = _json_list(team["scope_ids"])
        connection_ids = {
            str(connection_id) for connection_id in _json_list(team["connection_ids"])
        }
        inherited_scope_ids = [
            scope_id
            for connection_id in connection_ids
            for scope_id in connection_scope_ids.get(connection_id, [])
        ]
        merged_scope_ids = [*existing_scope_ids]
        merged_scope_ids.extend(
            scope_id for scope_id in inherited_scope_ids if scope_id not in merged_scope_ids
        )
        if merged_scope_ids != existing_scope_ids:
            bind.execute(
                sa.update(_team_profile)
                .where(_team_profile.c.id == team["id"])
                .values(scope_ids=merged_scope_ids)
            )


def _create_legacy_scopes(
    bind: sa.Connection,
    *,
    connection_id: object,
    selected_project_ids: list[object],
    selected_board_ids: list[object],
) -> list[str]:
    now = datetime.now(UTC).replace(tzinfo=None)
    scope_ids: list[str] = []
    for board_id in selected_board_ids:
        scope_id = uuid4()
        bind.execute(
            sa.insert(_scope_definition).values(
                connection_id=connection_id,
                name=f"Legacy board {board_id}",
                scope_type="board",
                external_ref={"id": str(board_id)},
                capabilities=["statuses", "labels", "sprint", "kanban"],
                id=scope_id,
                created_at=now,
                updated_at=now,
            )
        )
        scope_ids.append(str(scope_id))
    if scope_ids:
        return scope_ids
    for project_id in selected_project_ids:
        scope_id = uuid4()
        bind.execute(
            sa.insert(_scope_definition).values(
                connection_id=connection_id,
                name=f"Legacy project {project_id}",
                scope_type="project",
                external_ref={"id": str(project_id)},
                capabilities=["statuses", "labels"],
                id=scope_id,
                created_at=now,
                updated_at=now,
            )
        )
        scope_ids.append(str(scope_id))
    return scope_ids


def _json_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    return []
