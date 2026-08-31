# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.repositories.source_connections import create_source_connection
from em_radar_api.source_connections import ConnectorName, SourceConnectionCreate
from em_radar_api.tables import (
    TeamGitLabMemberTable,
    TeamGitLabRepositoryTable,
    TeamProfileTable,
)
from em_radar_connector_gitlab import (
    DISCOVERY_DEFAULT_WINDOW_DAYS,
    DISCOVERY_MIN_CANDIDATES,
    DISCOVERY_WIDE_WINDOW_DAYS,
)
from em_radar_core.connectors import (
    ConnectorAuthError,
    ConnectorError,
    MemberRef,
    RepositoryActivity,
    RepositoryRef,
)
from em_radar_core.models import ScopeVerificationStatus, WorkingMode


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _make_gitlab_connection(session_factory: sessionmaker[Session]) -> UUID:
    with session_factory() as session:
        conn = create_source_connection(
            session,
            SourceConnectionCreate(
                name=f"GitLab {uuid4().hex[:8]}",
                connector_name=ConnectorName.GITLAB,
            ),
        )
    return conn.id


def _make_team(
    session_factory: sessionmaker[Session],
    code_connection_id: UUID | None = None,
) -> UUID:
    now = datetime.now(UTC)
    with session_factory() as session:
        team = TeamProfileTable(
            name=f"Team {uuid4().hex[:8]}",
            working_mode=WorkingMode.SCRUM,
            connection_ids=[],
            scope_ids=[],
            signal_config_group_ids=[],
            code_connection_id=code_connection_id,
            created_at=now,
            updated_at=now,
        )
        session.add(team)
        session.commit()
        session.refresh(team)
        return team.id


def _make_mock_connector(
    *,
    get_user_return: MemberRef | None = None,
    get_project_return: RepositoryRef | None = None,
    search_users_return: list[MemberRef] | None = None,
    search_projects_return: list[RepositoryRef] | None = None,
    discover_repos_return: list[RepositoryActivity] | None = None,
    raise_auth_error: bool = False,
) -> MagicMock:
    connector = MagicMock()
    connector.close = AsyncMock()

    if raise_auth_error:
        connector.get_user = AsyncMock(side_effect=ConnectorAuthError("unauthorized"))
        connector.get_project = AsyncMock(side_effect=ConnectorAuthError("unauthorized"))
        connector.search_users = AsyncMock(side_effect=ConnectorAuthError("unauthorized"))
        connector.search_projects = AsyncMock(side_effect=ConnectorAuthError("unauthorized"))
        connector.discover_repositories_by_activity = AsyncMock(
            side_effect=ConnectorAuthError("unauthorized")
        )
    else:
        connector.get_user = AsyncMock(return_value=get_user_return)
        connector.get_project = AsyncMock(return_value=get_project_return)
        connector.search_users = AsyncMock(return_value=search_users_return or [])
        connector.search_projects = AsyncMock(return_value=search_projects_return or [])
        connector.discover_repositories_by_activity = AsyncMock(
            return_value=discover_repos_return or []
        )
    return connector


# ---------------------------------------------------------------------------
# gitlab_config_status
# ---------------------------------------------------------------------------


def test_gitlab_config_status_not_applicable_when_no_code_connection(
    api_client: TestClient,
) -> None:
    resp = api_client.post("/api/teams", json={"name": "No Code"})
    assert resp.status_code == 201
    assert resp.json()["gitlab_config_status"] == "not_applicable"


def test_gitlab_config_status_setup_required_when_code_connection_no_members(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    resp = api_client.get(f"/api/teams/{team_id}")
    assert resp.status_code == 200
    assert resp.json()["gitlab_config_status"] == "setup_required"


def test_gitlab_config_status_configured_when_member_saved(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        get_user_return=MemberRef(provider_user_id="10", username="dev", display_name="Dev User")
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    api_client.put(f"/api/teams/{team_id}/gitlab/members", json=[{"gitlab_user_id": 10}])

    resp = api_client.get(f"/api/teams/{team_id}")
    assert resp.json()["gitlab_config_status"] == "configured"


def test_gitlab_config_status_configured_when_repository_saved(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        get_project_return=RepositoryRef(
            provider_project_id="5",
            name="myrepo",
            path_with_namespace="group/myrepo",
        )
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    api_client.put(f"/api/teams/{team_id}/gitlab/repositories", json=[{"gitlab_project_id": 5}])

    resp = api_client.get(f"/api/teams/{team_id}")
    assert resp.json()["gitlab_config_status"] == "configured"


# ---------------------------------------------------------------------------
# GET /teams/{id}/gitlab/members
# ---------------------------------------------------------------------------


def test_list_gitlab_members_empty(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/members")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_gitlab_members_404_for_unknown_team(api_client: TestClient) -> None:
    resp = api_client.get(f"/api/teams/{uuid4()}/gitlab/members")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /teams/{id}/gitlab/members
# ---------------------------------------------------------------------------


def test_put_gitlab_members_persists_connector_resolved_values(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        get_user_return=MemberRef(
            provider_user_id="42",
            username="alice",
            display_name="Alice Smith",
            avatar_url=None,
        )
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/members",
        json=[{"gitlab_user_id": 42}],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["gitlab_user_id"] == 42
    assert data[0]["username"] == "alice"
    assert data[0]["display_name"] == "Alice Smith"
    assert data[0]["verification_status"] == "verified"
    assert UUID(data[0]["connection_id"]) == conn_id

    with session_factory() as session:
        rows = session.exec(
            __import__("sqlmodel")
            .select(TeamGitLabMemberTable)
            .where(TeamGitLabMemberTable.team_profile_id == team_id)
        ).all()
    assert len(rows) == 1
    assert rows[0].gitlab_user_id == 42
    assert rows[0].username == "alice"


def test_put_gitlab_members_unknown_id_returns_422_and_stores_nothing(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(get_user_return=None)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/members",
        json=[{"gitlab_user_id": 999}],
    )
    assert resp.status_code == 422

    with session_factory() as session:
        rows = session.exec(
            __import__("sqlmodel")
            .select(TeamGitLabMemberTable)
            .where(TeamGitLabMemberTable.team_profile_id == team_id)
        ).all()
    assert rows == []


def test_put_gitlab_members_replaces_existing(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock1 = _make_mock_connector(
        get_user_return=MemberRef(provider_user_id="1", username="user1", display_name="User One")
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock1,
    )
    api_client.put(f"/api/teams/{team_id}/gitlab/members", json=[{"gitlab_user_id": 1}])

    mock2 = _make_mock_connector(
        get_user_return=MemberRef(provider_user_id="2", username="user2", display_name="User Two")
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock2,
    )
    resp = api_client.put(f"/api/teams/{team_id}/gitlab/members", json=[{"gitlab_user_id": 2}])
    assert resp.status_code == 200

    with session_factory() as session:
        from sqlmodel import select

        rows = session.exec(
            select(TeamGitLabMemberTable).where(TeamGitLabMemberTable.team_profile_id == team_id)
        ).all()
    assert len(rows) == 1
    assert rows[0].gitlab_user_id == 2


def test_put_gitlab_members_replace_keeping_existing_id_succeeds(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-saving a set that retains an already-saved id must not hit the unique constraint."""
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock = _make_mock_connector(
        get_user_return=MemberRef(provider_user_id="x", username="u", display_name="U")
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock,
    )
    assert (
        api_client.put(
            f"/api/teams/{team_id}/gitlab/members", json=[{"gitlab_user_id": 1}]
        ).status_code
        == 200
    )
    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/members",
        json=[{"gitlab_user_id": 1}, {"gitlab_user_id": 2}],
    )
    assert resp.status_code == 200

    with session_factory() as session:
        from sqlmodel import select

        rows = session.exec(
            select(TeamGitLabMemberTable).where(TeamGitLabMemberTable.team_profile_id == team_id)
        ).all()
    assert sorted(r.gitlab_user_id for r in rows) == [1, 2]


def test_put_gitlab_members_duplicate_ids_in_body_are_deduplicated(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock = _make_mock_connector(
        get_user_return=MemberRef(provider_user_id="x", username="u", display_name="U")
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock,
    )
    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/members",
        json=[{"gitlab_user_id": 7}, {"gitlab_user_id": 7}],
    )
    assert resp.status_code == 200

    with session_factory() as session:
        from sqlmodel import select

        rows = session.exec(
            select(TeamGitLabMemberTable).where(TeamGitLabMemberTable.team_profile_id == team_id)
        ).all()
    assert [r.gitlab_user_id for r in rows] == [7]


def test_put_gitlab_repositories_replace_keeping_existing_id_succeeds(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock = _make_mock_connector(
        get_project_return=RepositoryRef(
            provider_project_id="x", name="r", path_with_namespace="g/r"
        )
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock,
    )
    assert (
        api_client.put(
            f"/api/teams/{team_id}/gitlab/repositories", json=[{"gitlab_project_id": 1}]
        ).status_code
        == 200
    )
    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/repositories",
        json=[{"gitlab_project_id": 1}, {"gitlab_project_id": 2}],
    )
    assert resp.status_code == 200

    with session_factory() as session:
        from sqlmodel import select

        rows = session.exec(
            select(TeamGitLabRepositoryTable).where(
                TeamGitLabRepositoryTable.team_profile_id == team_id
            )
        ).all()
    assert sorted(r.gitlab_project_id for r in rows) == [1, 2]


def test_put_gitlab_members_no_code_connection_returns_409(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    team_id = _make_team(session_factory, code_connection_id=None)

    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/members",
        json=[{"gitlab_user_id": 1}],
    )
    assert resp.status_code == 409


def test_put_gitlab_members_auth_error_returns_502(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(raise_auth_error=True)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/members",
        json=[{"gitlab_user_id": 1}],
    )
    assert resp.status_code == 502

    with session_factory() as session:
        from sqlmodel import select

        rows = session.exec(
            select(TeamGitLabMemberTable).where(TeamGitLabMemberTable.team_profile_id == team_id)
        ).all()
    assert rows == []


# ---------------------------------------------------------------------------
# GET /teams/{id}/gitlab/repositories
# ---------------------------------------------------------------------------


def test_list_gitlab_repositories_empty(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repositories")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# PUT /teams/{id}/gitlab/repositories
# ---------------------------------------------------------------------------


def test_put_gitlab_repositories_persists_connector_resolved_values(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        get_project_return=RepositoryRef(
            provider_project_id="7",
            name="backend",
            path_with_namespace="acme/backend",
        )
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/repositories",
        json=[{"gitlab_project_id": 7}],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["gitlab_project_id"] == 7
    assert data[0]["name"] == "backend"
    assert data[0]["path_with_namespace"] == "acme/backend"
    assert data[0]["verification_status"] == "verified"

    with session_factory() as session:
        from sqlmodel import select

        rows = session.exec(
            select(TeamGitLabRepositoryTable).where(
                TeamGitLabRepositoryTable.team_profile_id == team_id
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].gitlab_project_id == 7
    assert rows[0].name == "backend"


def test_put_gitlab_repositories_unknown_id_returns_422_and_stores_nothing(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(get_project_return=None)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/repositories",
        json=[{"gitlab_project_id": 999}],
    )
    assert resp.status_code == 422

    with session_factory() as session:
        from sqlmodel import select

        rows = session.exec(
            select(TeamGitLabRepositoryTable).where(
                TeamGitLabRepositoryTable.team_profile_id == team_id
            )
        ).all()
    assert rows == []


def test_put_gitlab_repositories_no_code_connection_returns_409(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    team_id = _make_team(session_factory, code_connection_id=None)

    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/repositories",
        json=[{"gitlab_project_id": 1}],
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /teams/{id}/gitlab/member-search
# ---------------------------------------------------------------------------


def test_member_search_proxies_to_connector(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        search_users_return=[
            MemberRef(provider_user_id="1", username="alice", display_name="Alice"),
            MemberRef(provider_user_id="2", username="bob", display_name="Bob"),
        ]
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-search?q=ali&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["username"] == "alice"
    assert data[1]["username"] == "bob"
    mock_connector.search_users.assert_awaited_once_with("ali", limit=10, page=1)


def test_member_search_caps_limit(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(search_users_return=[])
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    api_client.get(f"/api/teams/{team_id}/gitlab/member-search?q=x&limit=999")
    mock_connector.search_users.assert_awaited_once_with("x", limit=50, page=1)


def test_member_search_auth_error_is_502(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(raise_auth_error=True)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-search?q=x")
    assert resp.status_code == 502


def test_member_search_no_code_connection_returns_409(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    team_id = _make_team(session_factory, code_connection_id=None)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-search?q=x")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /teams/{id}/gitlab/project-search
# ---------------------------------------------------------------------------


def test_project_search_proxies_to_connector(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        search_projects_return=[
            RepositoryRef(
                provider_project_id="10",
                name="frontend",
                path_with_namespace="acme/frontend",
            ),
        ]
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/project-search?q=front&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["provider_project_id"] == "10"
    assert data[0]["name"] == "frontend"
    mock_connector.search_projects.assert_awaited_once_with("front", limit=5, page=1)


def test_project_search_auth_error_is_not_empty_list(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(raise_auth_error=True)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/project-search?q=x")
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /teams/{id}/gitlab/repository-suggestions
# ---------------------------------------------------------------------------


def test_repository_suggestions_returns_empty_when_no_saved_members(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector()
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_days"] == DISCOVERY_DEFAULT_WINDOW_DAYS
    assert data["repositories"] == []
    mock_connector.discover_repositories_by_activity.assert_not_awaited()


def test_repository_suggestions_returns_ranked_repos_from_connector(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    now = datetime.now(UTC)

    # Seed a member directly so the discovery endpoint has member_ids to pass.
    # Use DISCOVERY_MIN_CANDIDATES repos so the endpoint stays on the default window.
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=conn_id,
                gitlab_user_id=100,
                username="dev",
                display_name="Dev",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    activities = [
        RepositoryActivity(
            provider_project_id=str(i),
            name=f"service-{i}",
            path_with_namespace=f"acme/service-{i}",
            contributing_member_count=1,
            merge_request_count=i,
            last_activity_at=now,
        )
        for i in range(DISCOVERY_MIN_CANDIDATES)
    ]
    mock_connector = _make_mock_connector(discover_repos_return=activities)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_days"] == DISCOVERY_DEFAULT_WINDOW_DAYS
    repos = data["repositories"]
    assert len(repos) == DISCOVERY_MIN_CANDIDATES
    assert repos[0]["provider_project_id"] == "0"
    assert repos[0]["name"] == "service-0"

    mock_connector.discover_repositories_by_activity.assert_awaited_once()
    call_args = mock_connector.discover_repositories_by_activity.call_args
    assert call_args.args[0] == ["100"]
    assert call_args.kwargs["limit"] == 10


def test_repository_suggestions_no_code_connection_returns_409(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    team_id = _make_team(session_factory, code_connection_id=None)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions")
    assert resp.status_code == 409


def test_repository_suggestions_auth_error_is_502(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=conn_id,
                gitlab_user_id=1,
                username="dev",
                display_name="Dev",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    mock_connector = _make_mock_connector(raise_auth_error=True)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions")
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Fix 2: config status only counts VERIFIED rows on the current connection
# ---------------------------------------------------------------------------


def test_gitlab_config_status_setup_required_when_member_on_different_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    other_conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=other_conn_id,
                gitlab_user_id=100,
                username="stale_user",
                display_name="Stale User",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    resp = api_client.get(f"/api/teams/{team_id}")
    assert resp.status_code == 200
    assert resp.json()["gitlab_config_status"] == "setup_required"


def test_gitlab_config_status_setup_required_when_member_is_unavailable(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=conn_id,
                gitlab_user_id=100,
                username="unavail_user",
                display_name="Unavail User",
                verification_status=ScopeVerificationStatus.UNAVAILABLE,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    resp = api_client.get(f"/api/teams/{team_id}")
    assert resp.status_code == 200
    assert resp.json()["gitlab_config_status"] == "setup_required"


def test_list_teams_gitlab_config_status_setup_required_when_member_on_different_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    other_conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=other_conn_id,
                gitlab_user_id=200,
                username="stale_user",
                display_name="Stale User",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    resp = api_client.get("/api/teams")
    assert resp.status_code == 200
    team = next((t for t in resp.json() if t["id"] == str(team_id)), None)
    assert team is not None
    assert team["gitlab_config_status"] == "setup_required"


def test_list_teams_gitlab_config_status_setup_required_when_repo_is_unavailable(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabRepositoryTable(
                team_profile_id=team_id,
                connection_id=conn_id,
                gitlab_project_id=50,
                name="old-repo",
                path_with_namespace="org/old-repo",
                verification_status=ScopeVerificationStatus.UNAVAILABLE,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    resp = api_client.get("/api/teams")
    assert resp.status_code == 200
    team = next((t for t in resp.json() if t["id"] == str(team_id)), None)
    assert team is not None
    assert team["gitlab_config_status"] == "setup_required"


# ---------------------------------------------------------------------------
# Fix 3: repository suggestions exclude members on wrong connection / unavailable
# ---------------------------------------------------------------------------


def test_repository_suggestions_excludes_members_on_wrong_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    other_conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=conn_id,
                gitlab_user_id=100,
                username="valid_user",
                display_name="Valid User",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=other_conn_id,
                gitlab_user_id=200,
                username="stale_user",
                display_name="Stale User",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=conn_id,
                gitlab_user_id=300,
                username="unavail_user",
                display_name="Unavail User",
                verification_status=ScopeVerificationStatus.UNAVAILABLE,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    now = datetime.now(UTC)
    enough = [_make_activity(i, now) for i in range(DISCOVERY_MIN_CANDIDATES)]
    mock_connector = _make_mock_connector(discover_repos_return=enough)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions")
    assert resp.status_code == 200

    # Called once: enough candidates from the default window so no widening occurs.
    mock_connector.discover_repositories_by_activity.assert_awaited_once()
    call_args = mock_connector.discover_repositories_by_activity.call_args
    passed_ids = call_args.args[0]
    assert "100" in passed_ids
    assert "200" not in passed_ids
    assert "300" not in passed_ids


def test_repository_suggestions_returns_empty_when_all_members_stale(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    other_conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=other_conn_id,
                gitlab_user_id=999,
                username="stale_user",
                display_name="Stale User",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    mock_connector = _make_mock_connector()
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_days"] == DISCOVERY_DEFAULT_WINDOW_DAYS
    assert data["repositories"] == []
    mock_connector.discover_repositories_by_activity.assert_not_awaited()


# ---------------------------------------------------------------------------
# Fix 4: page parameter is forwarded through the search endpoints
# ---------------------------------------------------------------------------


def test_member_search_forwards_page_to_connector(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(search_users_return=[])
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    api_client.get(f"/api/teams/{team_id}/gitlab/member-search?q=ali&limit=10&page=2")
    mock_connector.search_users.assert_awaited_once_with("ali", limit=10, page=2)


def test_project_search_forwards_page_to_connector(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(search_projects_return=[])
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    api_client.get(f"/api/teams/{team_id}/gitlab/project-search?q=front&limit=5&page=2")
    mock_connector.search_projects.assert_awaited_once_with("front", limit=5, page=2)


# ---------------------------------------------------------------------------
# M9-12: Adaptive 90/180-day discovery window
# ---------------------------------------------------------------------------


def _seed_member(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    conn_id: UUID,
    gitlab_user_id: int = 100,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=conn_id,
                gitlab_user_id=gitlab_user_id,
                username="dev",
                display_name="Dev",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def _make_activity(i: int, now: datetime) -> RepositoryActivity:
    return RepositoryActivity(
        provider_project_id=str(i),
        name=f"repo-{i}",
        path_with_namespace=f"acme/repo-{i}",
        contributing_member_count=1,
        merge_request_count=i + 1,
        last_activity_at=now,
    )


def test_repository_suggestions_uses_default_window_when_enough_candidates(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the 90-day window returns >= DISCOVERY_MIN_CANDIDATES, use it and report window_days=90."""
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id)

    now = datetime.now(UTC)
    enough = [_make_activity(i, now) for i in range(DISCOVERY_MIN_CANDIDATES)]

    connector = _make_mock_connector(discover_repos_return=enough)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions?limit=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_days"] == DISCOVERY_DEFAULT_WINDOW_DAYS
    assert len(data["repositories"]) == DISCOVERY_MIN_CANDIDATES

    # Connector called exactly once (no widening needed).
    connector.discover_repositories_by_activity.assert_awaited_once()
    call_args = connector.discover_repositories_by_activity.call_args
    used_since: datetime = call_args.kwargs["since"]
    expected_since = now - timedelta(days=DISCOVERY_DEFAULT_WINDOW_DAYS)
    assert abs((used_since - expected_since).total_seconds()) < 5


def test_repository_suggestions_small_limit_does_not_force_widening(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller limit below the threshold must not force a widen: the endpoint fetches at least
    DISCOVERY_MIN_CANDIDATES to decide, then slices the response to the requested limit."""
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id)

    now = datetime.now(UTC)
    enough = [_make_activity(i, now) for i in range(DISCOVERY_MIN_CANDIDATES)]
    connector = _make_mock_connector(discover_repos_return=enough)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions?limit=1")
    assert resp.status_code == 200
    data = resp.json()
    # Default window kept (enough candidates existed within 90 days) despite the small limit.
    assert data["window_days"] == DISCOVERY_DEFAULT_WINDOW_DAYS
    assert len(data["repositories"]) == 1
    # Single connector call; it was asked for at least the threshold, not the raw limit of 1.
    connector.discover_repositories_by_activity.assert_awaited_once()
    assert connector.discover_repositories_by_activity.call_args.kwargs["limit"] >= (
        DISCOVERY_MIN_CANDIDATES
    )


def test_repository_suggestions_widens_to_wide_window_when_too_few_candidates(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the 90-day window returns < DISCOVERY_MIN_CANDIDATES, retry at 180 days and report that window."""
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id)

    now = datetime.now(UTC)
    # First call (90-day): fewer than the threshold.
    few = [_make_activity(i, now) for i in range(DISCOVERY_MIN_CANDIDATES - 1)]
    # Second call (180-day): more results.
    wide = [_make_activity(i, now) for i in range(DISCOVERY_MIN_CANDIDATES + 2)]

    connector = MagicMock()
    connector.close = AsyncMock()
    connector.discover_repositories_by_activity = AsyncMock(side_effect=[few, wide])

    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions?limit=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_days"] == DISCOVERY_WIDE_WINDOW_DAYS
    assert len(data["repositories"]) == DISCOVERY_MIN_CANDIDATES + 2

    # Connector called twice: once for each window.
    assert connector.discover_repositories_by_activity.await_count == 2
    first_call, second_call = connector.discover_repositories_by_activity.call_args_list

    first_since: datetime = first_call.kwargs["since"]
    expected_default_since = now - timedelta(days=DISCOVERY_DEFAULT_WINDOW_DAYS)
    assert abs((first_since - expected_default_since).total_seconds()) < 5

    second_since: datetime = second_call.kwargs["since"]
    expected_wide_since = now - timedelta(days=DISCOVERY_WIDE_WINDOW_DAYS)
    assert abs((second_since - expected_wide_since).total_seconds()) < 5


# ---------------------------------------------------------------------------
# M9-13: POST /teams/{id}/gitlab/member-resolve (bulk resolve)
# ---------------------------------------------------------------------------


def test_bulk_resolve_classifies_matched_entry(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        search_users_return=[
            MemberRef(provider_user_id="10", username="alice", display_name="Alice"),
        ]
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["alice"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["entry"] == "alice"
    assert result["status"] == "matched"
    assert result["match"]["username"] == "alice"
    assert result["candidates"] == []


def test_bulk_resolve_classifies_ambiguous_entry(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        search_users_return=[
            MemberRef(provider_user_id="20", username="bsmith", display_name="Bob Smith"),
            MemberRef(provider_user_id="21", username="bobsmth", display_name="Bob Smth"),
        ]
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["bob smith"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["entry"] == "bob smith"
    assert result["status"] == "ambiguous"
    assert result["match"] is None
    assert len(result["candidates"]) == 2
    usernames = {c["username"] for c in result["candidates"]}
    assert "bsmith" in usernames
    assert "bobsmth" in usernames


def test_bulk_resolve_classifies_unmatched_entry(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(search_users_return=[])
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["unknown-person"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["entry"] == "unknown-person"
    assert result["status"] == "unmatched"
    assert result["match"] is None
    assert result["candidates"] == []


def test_bulk_resolve_skips_blank_entries(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(
        search_users_return=[
            MemberRef(provider_user_id="1", username="alice", display_name="Alice"),
        ]
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["", "  ", "alice", ""]},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Only the non-blank entry should produce a result.
    assert len(data["results"]) == 1
    assert data["results"][0]["entry"] == "alice"


def test_bulk_resolve_no_code_connection_returns_409(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    team_id = _make_team(session_factory, code_connection_id=None)

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["alice"]},
    )
    assert resp.status_code == 409


def test_bulk_resolve_auth_error_returns_502(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(raise_auth_error=True)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["alice"]},
    )
    assert resp.status_code == 502
    # The connector must still be closed even when a search raises.
    mock_connector.close.assert_awaited()


def test_bulk_resolve_generic_connector_error_returns_502_and_closes(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-auth ConnectorError (e.g. permission/network) also maps to 502, and closes."""
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector()
    mock_connector.search_users = AsyncMock(side_effect=ConnectorError("boom"))
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["alice"]},
    )
    assert resp.status_code == 502
    mock_connector.close.assert_awaited()


def test_bulk_resolve_rejects_too_many_entries(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """A paste exceeding the entry cap is rejected (422) before any connector search runs."""
    from em_radar_api.team_profiles import BULK_RESOLVE_MAX_ENTRIES

    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": [f"user{i}" for i in range(BULK_RESOLVE_MAX_ENTRIES + 1)]},
    )
    assert resp.status_code == 422


def test_bulk_resolve_rejects_overlong_entry(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """An entry exceeding the per-entry length cap is rejected (422)."""
    from em_radar_api.team_profiles import BULK_RESOLVE_MAX_ENTRY_LENGTH

    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    resp = api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["a" * (BULK_RESOLVE_MAX_ENTRY_LENGTH + 1)]},
    )
    assert resp.status_code == 422


def test_bulk_resolve_caps_per_entry_search_limit(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoint must pass the bounded per-entry limit to search_users (§24)."""
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_connector(search_users_return=[])
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    api_client.post(
        f"/api/teams/{team_id}/gitlab/member-resolve",
        json={"entries": ["alice"]},
    )
    # search_users must have been called with a small bounded limit, not unbounded.
    call_kwargs = mock_connector.search_users.call_args
    used_limit = call_kwargs.kwargs.get("limit") or call_kwargs.args[1]
    assert used_limit <= 10
