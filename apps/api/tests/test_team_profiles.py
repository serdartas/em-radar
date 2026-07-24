from pathlib import Path
from typing import ClassVar
from uuid import UUID, uuid4

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
from em_radar_api.tables import TeamProfileTable
from em_radar_core.connectors import Capabilities, ConnectionTestResult
from em_radar_core.models import TeamProfile as CanonicalTeamProfile

REPO_ROOT = Path(__file__).parents[3]


class _FakeGitLabConnector:
    """Minimal MR-capable connector used only in tests."""

    name: ClassVar[str] = "gitlab"
    display_name: ClassVar[str] = "GitLab (test)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        pass

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="ok")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        return Capabilities(provides_mergerequests=True, provides_repositories=True)

    async def close(self) -> None:
        pass


class _FakeJiraMRConnector:
    """Fake Jira connector that (artificially) provides MR data — only used in tests that need
    to switch between two MR-capable connectors to verify the update guard allows the change."""

    name: ClassVar[str] = "jira"
    display_name: ClassVar[str] = "Jira (test MR)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        pass

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="ok")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        return Capabilities(provides_mergerequests=True)

    async def close(self) -> None:
        pass


class _FakeTicketingConnector:
    """Registered ticketing-only connector (provides_mergerequests=False).

    Used to exercise the `not caps.provides_mergerequests` branch of the connector_name
    change guard, as distinct from the `caps is None` (unregistered) branch.
    """

    name: ClassVar[str] = "jira"
    display_name: ClassVar[str] = "Jira (test ticketing only)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        pass

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="ok")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        return Capabilities(provides_mergerequests=False, provides_workitems=True)

    async def close(self) -> None:
        pass


def _connection_id(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        connection = create_source_connection(
            session,
            SourceConnectionCreate(
                name=f"Jira {uuid4().hex[:8]}",
                connector_name=ConnectorName.JIRA,
            ),
        )
    return str(connection.id)


def _gitlab_connection_id(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        connection = create_source_connection(
            session,
            SourceConnectionCreate(
                name=f"GitLab {uuid4().hex[:8]}",
                connector_name=ConnectorName.GITLAB,
            ),
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


def test_board_scope_connection_is_derived_not_caller_supplied(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    scope_connection = _connection_id(session_factory)
    _other_connection = _connection_id(session_factory)
    board = _create_board_scope(api_client, scope_connection, "Board A")

    # connection_ids is server-derived from scope_ids; the caller's value is ignored.
    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [_other_connection],
            "scope_ids": [board],
        },
    )

    assert response.status_code == 201
    # Derived connection_ids = scope_connection (from the board scope).
    assert response.json()["connection_ids"] == [scope_connection]


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


def test_migration_adds_code_connection_id_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "team-code-conn.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))
    command.upgrade(Config(REPO_ROOT / "alembic.ini"), "head")

    columns = {
        column["name"]: column
        for column in inspect(create_db_engine(database_path)).get_columns("team_profile")
    }
    assert "code_connection_id" in columns
    assert columns["code_connection_id"]["nullable"] is True


def test_null_code_connection_id_is_allowed(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": None},
    )

    assert response.status_code == 201
    assert response.json()["code_connection_id"] is None


def test_nonexistent_code_connection_id_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": str(uuid4())},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "code_connection_id must reference an existing connection"


def test_ticketing_only_connection_rejected_as_code_source(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    jira_id = _connection_id(session_factory)

    response = api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": jira_id},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "code_connection_id must reference a connection that provides merge-request data"
    )


def test_mr_capable_connection_accepted_as_code_source(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector],
    )
    gitlab_id = _gitlab_connection_id(session_factory)

    response = api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": gitlab_id},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["code_connection_id"] == gitlab_id
    # code_connection_id must be merged into connection_ids automatically.
    assert gitlab_id in data["connection_ids"]


def test_attaching_code_connection_alongside_board_scope(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attaching a code connection PRESERVES the board scope's connection in connection_ids."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector],
    )
    jira_id = _connection_id(session_factory)
    gitlab_id = _gitlab_connection_id(session_factory)
    board = _create_board_scope(api_client, jira_id, "Board A")

    # Create a team with a board scope (connection_ids derives to [jira_id]).
    created = api_client.post(
        "/api/teams",
        json={"name": "Platform", "scope_ids": [board]},
    ).json()
    assert jira_id in created["connection_ids"]

    # Attach the GitLab code source — should NOT drop the board connection.
    response = api_client.patch(
        f"/api/teams/{created['id']}",
        json={"code_connection_id": gitlab_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code_connection_id"] == gitlab_id
    assert jira_id in data["connection_ids"]
    assert gitlab_id in data["connection_ids"]


def test_adding_board_scope_preserves_code_connection_id(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attaching a board scope PRESERVES an existing code connection in connection_ids."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector],
    )
    jira_id = _connection_id(session_factory)
    gitlab_id = _gitlab_connection_id(session_factory)
    board = _create_board_scope(api_client, jira_id, "Board A")

    # Create a team with just the code source (connection_ids derives to [gitlab_id]).
    created = api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": gitlab_id},
    ).json()
    assert created["connection_ids"] == [gitlab_id]

    # Attach the board scope — code connection must be preserved.
    response = api_client.patch(
        f"/api/teams/{created['id']}",
        json={"scope_ids": [board]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code_connection_id"] == gitlab_id
    assert jira_id in data["connection_ids"]
    assert gitlab_id in data["connection_ids"]


def test_switching_code_connection_removes_orphaned_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching code connection A→B removes A from connection_ids (no orphans)."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector],
    )
    gitlab_a = _gitlab_connection_id(session_factory)
    gitlab_b = _gitlab_connection_id(session_factory)

    created = api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": gitlab_a},
    ).json()
    assert gitlab_a in created["connection_ids"]

    response = api_client.patch(
        f"/api/teams/{created['id']}",
        json={"code_connection_id": gitlab_b},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code_connection_id"] == gitlab_b
    assert gitlab_b in data["connection_ids"]
    assert gitlab_a not in data["connection_ids"]


def test_detaching_code_connection_removes_it_from_connection_ids(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector],
    )
    gitlab_id = _gitlab_connection_id(session_factory)

    created = api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": gitlab_id},
    ).json()
    assert gitlab_id in created["connection_ids"]

    response = api_client.patch(
        f"/api/teams/{created['id']}",
        json={"code_connection_id": None},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code_connection_id"] is None
    assert gitlab_id not in data["connection_ids"]


def test_code_only_connection_deletion_blocked_by_team_guard(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection referenced only via code_connection_id (no scope) cannot be deleted.

    This exercises the _referencing_teams deletion guard, which is the only remaining
    protection for code-only connections (the _referencing_scopes guard does not fire
    when there is no ScopeDefinition for the connection).
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector],
    )
    gitlab_id = _gitlab_connection_id(session_factory)

    # Attach the connection ONLY via code_connection_id — no board scope, so no
    # ScopeDefinition references it.  The derived connection_ids will contain gitlab_id.
    api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": gitlab_id},
    )

    response = api_client.delete(f"/api/connections/{gitlab_id}")

    assert response.status_code == 409
    assert "referenced by a team" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Finding 1: connector_name change guard for code-source connections
# ---------------------------------------------------------------------------


def test_changing_code_source_connector_to_non_mr_capable_is_rejected(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing connector_name of a code-source connection to a ticketing-only connector
    must be rejected — it would leave code_connection_id pointing at a non-MR-capable conn.

    Both connectors are registered so get_connector_capabilities("jira") returns a real
    Capabilities with provides_mergerequests=False, exercising that branch (not caps is None).
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector, _FakeTicketingConnector],
    )
    gitlab_id = _gitlab_connection_id(session_factory)
    api_client.post("/api/teams", json={"name": "Platform", "code_connection_id": gitlab_id})

    response = api_client.patch(
        f"/api/connections/{gitlab_id}",
        json={"connector_name": "jira"},
    )

    assert response.status_code == 409
    assert "non-MR-capable" in response.json()["detail"]


def test_changing_code_source_connector_to_another_mr_capable_is_allowed(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing connector_name to another MR-capable connector is permitted."""
    # Both connectors report provides_mergerequests=True in this test.
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeJiraMRConnector, _FakeGitLabConnector],
    )
    jira_id = _connection_id(session_factory)
    # With the fake Jira connector providing MR, we can set it as code source.
    api_client.post("/api/teams", json={"name": "Platform", "code_connection_id": jira_id})

    # Switch to gitlab — also MR-capable in this test.
    response = api_client.patch(
        f"/api/connections/{jira_id}",
        json={"connector_name": "gitlab"},
    )

    assert response.status_code == 200
    assert response.json()["connector_name"] == "gitlab"


def test_changing_connector_name_on_non_code_source_connection_is_unaffected(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new guard does not block connector_name changes on connections not used as code source."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector],
    )
    gitlab_id = _gitlab_connection_id(session_factory)
    # No team uses this connection as code_connection_id.

    response = api_client.patch(
        f"/api/connections/{gitlab_id}",
        json={"connector_name": "jira"},
    )

    assert response.status_code == 200
    assert response.json()["connector_name"] == "jira"


# ---------------------------------------------------------------------------
# Finding 2: canonical TeamProfile must preserve code_connection_id
# ---------------------------------------------------------------------------


def test_canonical_team_profile_preserves_code_connection_id(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TeamProfile.model_validate(team_row) must carry code_connection_id through.

    Guards against the regression where the canonical TeamProfile lacked the field and
    model_validate silently dropped it, breaking EvaluationContext.team.code_connection_id.
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabConnector],
    )
    gitlab_id = _gitlab_connection_id(session_factory)

    created = api_client.post(
        "/api/teams",
        json={"name": "Platform", "code_connection_id": gitlab_id},
    ).json()

    with session_factory() as session:
        row = session.get(TeamProfileTable, UUID(created["id"]))
        assert row is not None
        canonical = CanonicalTeamProfile.model_validate(row, from_attributes=True)

    assert canonical.code_connection_id == UUID(gitlab_id)
