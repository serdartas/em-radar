from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.db import DATABASE_PATH_ENV, create_db_engine
from em_radar_api.repositories.source_connections import create_source_connection
from em_radar_api.source_connections import ConnectorName, SourceConnectionCreate

REPO_ROOT = Path(__file__).parents[3]


def _connection_id(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        connection = create_source_connection(
            session,
            SourceConnectionCreate(connector_name=ConnectorName.JIRA),
        )
    return str(connection.id)


def _create_board_scope(api_client: TestClient, connection_id: str, name: str) -> str:
    response = api_client.post(
        "/api/scopes",
        json={
            "connection_id": connection_id,
            "name": name,
            "scope_type": "board",
            "external_ref": {},
            "capabilities": [],
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_group(api_client: TestClient, name: str = "Backend signals") -> str:
    response = api_client.post("/api/signal-config-groups", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_team_defaults_signal_config_group_ids_to_empty(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/teams",
        json={"name": "Platform", "project_ids": [], "repository_ids": []},
    )

    assert response.status_code == 201
    assert response.json()["signal_config_group_ids"] == []


def test_attaching_existing_group_succeeds(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    connection_id = _connection_id(session_factory)
    group_id = _create_group(api_client)

    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [connection_id],
            "signal_config_group_ids": [group_id],
        },
    )

    assert response.status_code == 201
    assert response.json()["signal_config_group_ids"] == [group_id]


def test_attaching_nonexistent_group_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/teams",
        json={"name": "Platform", "signal_config_group_ids": [str(uuid4())]},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "signal_config_group_ids must reference existing signal config groups"
    )


def test_second_board_scope_is_rejected(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    connection_id = _connection_id(session_factory)
    board_a = _create_board_scope(api_client, connection_id, "Board A")
    board_b = _create_board_scope(api_client, connection_id, "Board B")

    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [connection_id],
            "scope_ids": [board_a, board_b],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "scope_ids may contain at most one board scope"


def test_same_board_scope_listed_twice_is_rejected(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    connection_id = _connection_id(session_factory)
    board = _create_board_scope(api_client, connection_id, "Board A")

    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [connection_id],
            "scope_ids": [board, board],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "scope_ids may contain at most one board scope"


def test_single_board_scope_is_accepted(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    connection_id = _connection_id(session_factory)
    board = _create_board_scope(api_client, connection_id, "Board A")

    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [connection_id],
            "scope_ids": [board],
        },
    )

    assert response.status_code == 201
    assert response.json()["scope_ids"] == [board]


def test_attaching_group_via_patch(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    group_id = _create_group(api_client)
    created = api_client.post(
        "/api/teams",
        json={"name": "Platform", "project_ids": [], "repository_ids": []},
    ).json()

    response = api_client.patch(
        f"/api/teams/{created['id']}",
        json={"signal_config_group_ids": [group_id]},
    )

    assert response.status_code == 200
    assert response.json()["signal_config_group_ids"] == [group_id]


def test_patch_attaching_nonexistent_group_is_rejected(api_client: TestClient) -> None:
    created = api_client.post(
        "/api/teams",
        json={"name": "Platform", "project_ids": [], "repository_ids": []},
    ).json()

    response = api_client.patch(
        f"/api/teams/{created['id']}",
        json={"signal_config_group_ids": [str(uuid4())]},
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "signal_config_group_ids must reference existing signal config groups"
    )


def test_duplicate_group_ids_are_rejected(api_client: TestClient) -> None:
    group_id = _create_group(api_client)

    response = api_client.post(
        "/api/teams",
        json={"name": "Platform", "signal_config_group_ids": [group_id, group_id]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "signal_config_group_ids must not contain duplicates"


def test_board_scope_must_belong_to_team_connection(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    scope_connection = _connection_id(session_factory)
    other_connection = _connection_id(session_factory)
    board = _create_board_scope(api_client, scope_connection, "Board A")

    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [other_connection],
            "scope_ids": [board],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "scope_ids must reference the selected connections"


def test_migration_adds_signal_config_group_ids_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "team-groups.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))
    command.upgrade(Config(REPO_ROOT / "alembic.ini"), "head")

    columns = {
        column["name"]: column
        for column in inspect(create_db_engine(database_path)).get_columns("team_profile")
    }
    assert "signal_config_group_ids" in columns
    assert columns["signal_config_group_ids"]["nullable"] is False
