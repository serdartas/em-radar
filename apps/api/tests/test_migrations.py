import json
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy import inspect

from em_radar_api.db import DATABASE_PATH_ENV, create_db_engine

EXPECTED_TABLES = {
    "alembic_version",
    "board",
    "comment",
    "evaluation_window",
    "merge_request",
    "project",
    "report",
    "repository",
    "review",
    "signal_config_group",
    "signal_definition",
    "signal_finding",
    "signal_pack_history",
    "scope_definition",
    "source_connection",
    "sprint",
    "team_profile",
    "transition",
    "user",
    "work_item",
    "work_item_link",
}
REPO_ROOT = Path(__file__).parents[3]


def test_baseline_migration_round_trips_and_matches_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "migration.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))
    config = Config(REPO_ROOT / "alembic.ini")

    command.upgrade(config, "head")
    assert set(inspect(create_db_engine(database_path)).get_table_names()) == EXPECTED_TABLES

    command.downgrade(config, "base")
    assert inspect(create_db_engine(database_path)).get_table_names() == ["alembic_version"]

    command.upgrade(config, "head")
    command.check(config)


def test_scope_definition_migration_backfills_legacy_team_board_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "legacy-scope.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))
    config = Config(REPO_ROOT / "alembic.ini")

    command.upgrade(config, "5aa998bb48f2")
    engine = create_db_engine(database_path)
    connection_id = uuid4()
    team_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO source_connection (
                    connector_name,
                    config,
                    selected_project_ids,
                    selected_board_ids,
                    selected_repository_ids,
                    id,
                    created_at
                )
                VALUES (
                    'jira',
                    '{}',
                    '["PROJ"]',
                    '["42"]',
                    '[]',
                    :connection_id,
                    '2026-01-01 00:00:00'
                )
                """
            ),
            {"connection_id": connection_id.hex},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO team_profile (
                    id,
                    name,
                    description,
                    connection_ids,
                    project_ids,
                    board_ids,
                    repository_ids,
                    working_mode,
                    sprint_length_days,
                    member_user_keys,
                    created_at,
                    updated_at
                )
                VALUES (
                    :team_id,
                    'Legacy Team',
                    NULL,
                    :connection_ids,
                    '[]',
                    '[]',
                    '[]',
                    'SCRUM',
                    14,
                    '[]',
                    '2026-01-01 00:00:00',
                    '2026-01-01 00:00:00'
                )
                """
            ),
            {"team_id": team_id.hex, "connection_ids": f'["{connection_id}"]'},
        )

    command.upgrade(config, "8b723e4c5f1a")

    with engine.connect() as connection:
        scope = connection.execute(sa.text("SELECT * FROM scope_definition")).mappings().one()
        team_scope_ids = connection.execute(
            sa.text("SELECT scope_ids FROM team_profile WHERE id = :team_id"),
            {"team_id": team_id.hex},
        ).scalar_one()

    assert scope["connection_id"] in {connection_id.hex, str(connection_id)}
    assert scope["scope_type"] == "board"
    external_ref = (
        json.loads(scope["external_ref"])
        if isinstance(scope["external_ref"], str)
        else scope["external_ref"]
    )
    parsed_team_scope_ids = (
        json.loads(team_scope_ids) if isinstance(team_scope_ids, str) else team_scope_ids
    )
    assert external_ref == {"id": "42"}
    assert str(scope["id"]) in {
        str(scope_id).replace("-", "") for scope_id in parsed_team_scope_ids
    }
