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
    "report_job",
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


def test_sprint_label_migration_backfills_existing_sprint_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upgrading to f2b3c4d5e6a7 backfills sprint_label for pre-existing sprint windows."""
    database_path = tmp_path / "sprint-label.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))
    config = Config(REPO_ROOT / "alembic.ini")

    # Upgrade to the revision just before sprint_label is added.
    command.upgrade(config, "a1b2c3d4e5f6")
    engine = create_db_engine(database_path)

    project_id = uuid4()
    board_id = uuid4()
    sprint_id = uuid4()
    team_id = uuid4()
    window_id = uuid4()

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO team_profile (id, name, connection_ids, scope_ids, project_ids,"
                " board_ids, repository_ids, signal_config_group_ids, working_mode,"
                " member_user_keys, created_at, updated_at)"
                " VALUES (:id, 'T', '[]', '[]', '[]', '[]', '[]', '[]', 'KANBAN',"
                " '[]', '2026-01-01', '2026-01-01')"
            ),
            {"id": team_id.hex},
        )
        conn.execute(
            sa.text(
                "INSERT INTO project (id, source, external_id, key, name, fetched_at)"
                " VALUES (:id, 'JIRA', 'p-1', 'PROJ', 'My Project', '2026-01-01')"
            ),
            {"id": project_id.hex},
        )
        conn.execute(
            sa.text(
                "INSERT INTO board (id, source, external_id, project_id, name, fetched_at)"
                " VALUES (:id, 'JIRA', 'b-1', :project_id, 'My Board', '2026-01-01')"
            ),
            {"id": board_id.hex, "project_id": project_id.hex},
        )
        conn.execute(
            sa.text(
                "INSERT INTO sprint (id, source, external_id, board_id, name, state, fetched_at)"
                " VALUES (:id, 'JIRA', 'sp-1', :board_id, 'Sprint 99', 'ACTIVE', '2026-01-01')"
            ),
            {"id": sprint_id.hex, "board_id": board_id.hex},
        )
        conn.execute(
            sa.text(
                "INSERT INTO evaluation_window"
                " (id, window_type, team_profile_id, sprint_id)"
                " VALUES (:id, 'SPRINT', :team_id, :sprint_id)"
            ),
            {"id": window_id.hex, "team_id": team_id.hex, "sprint_id": sprint_id.hex},
        )

    # Apply the sprint_label migration.
    command.upgrade(config, "f2b3c4d5e6a7")

    with engine.connect() as conn:
        label = conn.execute(
            sa.text("SELECT sprint_label FROM evaluation_window WHERE id = :id"),
            {"id": window_id.hex},
        ).scalar_one()

    assert label == "Sprint 99"
