# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.repositories.scope_definitions import create_scope_definition
from em_radar_api.repositories.source_connections import create_source_connection
from em_radar_api.scope_definitions import ScopeDefinitionCreate, ScopeType
from em_radar_api.source_connections import ConnectorName, SourceConnectionCreate
from em_radar_api.tables import TeamProfileTable
from em_radar_core.connectors import ConnectorAuthError, MemberRef
from em_radar_core.models import WorkingMode


# ---------------------------------------------------------------------------
# Fixtures helpers
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


def _make_jira_connection(session_factory: sessionmaker[Session]) -> UUID:
    with session_factory() as session:
        conn = create_source_connection(
            session,
            SourceConnectionCreate(
                name=f"Jira {uuid4().hex[:8]}",
                connector_name=ConnectorName.JIRA,
            ),
        )
    return conn.id


def _make_team(
    session_factory: sessionmaker[Session],
    code_connection_id: UUID | None = None,
    connection_ids: list[UUID] | None = None,
) -> UUID:
    now = datetime.now(UTC)
    with session_factory() as session:
        team = TeamProfileTable(
            name=f"Team {uuid4().hex[:8]}",
            working_mode=WorkingMode.SCRUM,
            connection_ids=connection_ids or [],
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


def _fake_jira_person(
    display_name: str,
    email_address: str | None = None,
    account_id: str | None = None,
) -> object:
    """Build a mock JiraPersonRef-like object."""
    obj = MagicMock()
    obj.display_name = display_name
    obj.email_address = email_address
    obj.account_id = account_id
    return obj


def _make_mock_jira_connector(
    *,
    recently_active: list[object] | None = None,
    raise_error: bool = False,
) -> MagicMock:
    connector = MagicMock()
    connector.close = AsyncMock()
    if raise_error:
        connector.list_recently_active_users = AsyncMock(
            side_effect=ConnectorAuthError("unauthorized")
        )
    else:
        connector.list_recently_active_users = AsyncMock(return_value=recently_active or [])
    return connector


def _make_mock_gitlab_connector(
    *,
    search_results: list[MemberRef] | None = None,
    raise_error: bool = False,
) -> MagicMock:
    connector = MagicMock()
    connector.close = AsyncMock()
    # Both methods are required by the MemberProvider protocol for isinstance to pass.
    connector.get_user = AsyncMock(return_value=None)
    if raise_error:
        connector.search_users = AsyncMock(side_effect=ConnectorAuthError("gl-unauth"))
    else:
        connector.search_users = AsyncMock(return_value=search_results or [])
    return connector


# ---------------------------------------------------------------------------
# GET /teams/{id}/gitlab/member-suggestions
# ---------------------------------------------------------------------------


def test_member_suggestions_returns_404_for_unknown_team(api_client: TestClient) -> None:
    resp = api_client.get(f"/api/teams/{uuid4()}/gitlab/member-suggestions")
    assert resp.status_code == 404


def test_member_suggestions_returns_409_when_no_gitlab_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    team_id = _make_team(session_factory, code_connection_id=None)
    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 409


def test_member_suggestions_returns_empty_when_no_jira_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    """Team with GitLab but no Jira: gracefully return empty suggestions."""
    gl_id = _make_gitlab_connection(session_factory)
    # connection_ids is empty — no Jira
    team_id = _make_team(session_factory, code_connection_id=gl_id, connection_ids=[])
    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []
    assert data["window_days"] > 0


def test_member_suggestions_returns_empty_when_jira_returns_no_users(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gl_id = _make_gitlab_connection(session_factory)
    jira_id = _make_jira_connection(session_factory)
    team_id = _make_team(
        session_factory,
        code_connection_id=gl_id,
        connection_ids=[jira_id],
    )

    mock_jira = _make_mock_jira_connector(recently_active=[])
    mock_gitlab = _make_mock_gitlab_connector()

    call_count = {"n": 0}

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        call_count["n"] += 1
        if cid == jira_id:
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []


def test_member_suggestions_high_confidence_when_single_gitlab_match(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly one GitLab result → confidence=high, match is set."""
    gl_id = _make_gitlab_connection(session_factory)
    jira_id = _make_jira_connection(session_factory)
    team_id = _make_team(
        session_factory,
        code_connection_id=gl_id,
        connection_ids=[jira_id],
    )

    mock_jira = _make_mock_jira_connector(
        recently_active=[
            _fake_jira_person("Alice Smith", email_address="alice@example.com", account_id="acc-1"),
        ]
    )
    mock_gitlab = _make_mock_gitlab_connector(
        search_results=[
            MemberRef(
                provider_user_id="42",
                username="alice.smith",
                display_name="Alice Smith",
                avatar_url=None,
            )
        ]
    )

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        if cid == jira_id:
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) == 1
    s = data["suggestions"][0]
    assert s["confidence"] == "high"
    assert s["jira_person"]["display_name"] == "Alice Smith"
    assert s["jira_person"]["email_address"] == "alice@example.com"
    assert s["jira_person"]["account_id"] == "acc-1"
    assert s["match"] is not None
    assert s["match"]["username"] == "alice.smith"
    assert s["candidates"] == []


def test_member_suggestions_uncertain_when_multiple_gitlab_matches(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple GitLab results → confidence=uncertain, candidates list is populated."""
    gl_id = _make_gitlab_connection(session_factory)
    jira_id = _make_jira_connection(session_factory)
    team_id = _make_team(
        session_factory,
        code_connection_id=gl_id,
        connection_ids=[jira_id],
    )

    mock_jira = _make_mock_jira_connector(
        recently_active=[
            _fake_jira_person("Bob Jones"),
        ]
    )
    mock_gitlab = _make_mock_gitlab_connector(
        search_results=[
            MemberRef(
                provider_user_id="10",
                username="bob.j",
                display_name="Bob J",
                avatar_url=None,
            ),
            MemberRef(
                provider_user_id="11",
                username="bob.jones2",
                display_name="Bob Jones II",
                avatar_url=None,
            ),
        ]
    )

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        if cid == jira_id:
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) == 1
    s = data["suggestions"][0]
    assert s["confidence"] == "uncertain"
    assert s["match"] is None
    assert len(s["candidates"]) == 2
    usernames = {c["username"] for c in s["candidates"]}
    assert "bob.j" in usernames
    assert "bob.jones2" in usernames


def test_member_suggestions_uncertain_when_no_gitlab_match(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero GitLab results → confidence=uncertain, candidates is empty list."""
    gl_id = _make_gitlab_connection(session_factory)
    jira_id = _make_jira_connection(session_factory)
    team_id = _make_team(
        session_factory,
        code_connection_id=gl_id,
        connection_ids=[jira_id],
    )

    mock_jira = _make_mock_jira_connector(recently_active=[_fake_jira_person("Charlie Nobody")])
    mock_gitlab = _make_mock_gitlab_connector(search_results=[])

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        if cid == jira_id:
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) == 1
    s = data["suggestions"][0]
    assert s["confidence"] == "uncertain"
    assert s["match"] is None
    assert s["candidates"] == []


def test_member_suggestions_returns_502_on_jira_connector_error(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gl_id = _make_gitlab_connection(session_factory)
    jira_id = _make_jira_connection(session_factory)
    team_id = _make_team(
        session_factory,
        code_connection_id=gl_id,
        connection_ids=[jira_id],
    )

    mock_jira = _make_mock_jira_connector(raise_error=True)
    mock_gitlab = _make_mock_gitlab_connector()

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        if cid == jira_id:
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 502


def test_member_suggestions_returns_502_on_gitlab_search_error(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gl_id = _make_gitlab_connection(session_factory)
    jira_id = _make_jira_connection(session_factory)
    team_id = _make_team(
        session_factory,
        code_connection_id=gl_id,
        connection_ids=[jira_id],
    )

    mock_jira = _make_mock_jira_connector(recently_active=[_fake_jira_person("Dave Error")])
    mock_gitlab = _make_mock_gitlab_connector(raise_error=True)

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        if cid == jira_id:
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 502


def test_member_suggestions_skips_jira_person_with_empty_display_name(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Jira people with no display_name or email are silently skipped."""
    gl_id = _make_gitlab_connection(session_factory)
    jira_id = _make_jira_connection(session_factory)
    team_id = _make_team(
        session_factory,
        code_connection_id=gl_id,
        connection_ids=[jira_id],
    )

    nameless = _fake_jira_person("", email_address=None, account_id=None)
    mock_jira = _make_mock_jira_connector(recently_active=[nameless])
    mock_gitlab = _make_mock_gitlab_connector()

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        if cid == jira_id:
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []
    # GitLab search must not have been called for a nameless Jira person.
    mock_gitlab.search_users.assert_not_awaited()


def _make_jira_project_scope(
    session_factory: sessionmaker[Session],
    jira_connection_id: UUID,
    project_key: str,
) -> UUID:
    with session_factory() as session:
        scope = create_scope_definition(
            session,
            ScopeDefinitionCreate(
                connection_id=jira_connection_id,
                name=f"Project {project_key}",
                scope_type=ScopeType.PROJECT,
                external_ref={"key": project_key, "id": "10000"},
                capabilities=["statuses"],
            ),
        )
    return scope.id


def test_member_suggestions_passes_project_keys_from_scope(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Project keys from the team's Jira project scopes are forwarded to list_recently_active_users."""
    gl_id = _make_gitlab_connection(session_factory)
    jira_id = _make_jira_connection(session_factory)
    scope_id = _make_jira_project_scope(session_factory, jira_id, "ENG")
    now = datetime.now(UTC)
    with session_factory() as session:
        team = TeamProfileTable(
            name=f"Team {uuid4().hex[:8]}",
            working_mode=WorkingMode.SCRUM,
            connection_ids=[jira_id],
            scope_ids=[scope_id],
            signal_config_group_ids=[],
            code_connection_id=gl_id,
            created_at=now,
            updated_at=now,
        )
        session.add(team)
        session.commit()
        session.refresh(team)
        team_id = team.id

    mock_jira = _make_mock_jira_connector(recently_active=[])
    mock_gitlab = _make_mock_gitlab_connector()

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        if cid == jira_id:
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 200
    # The connector must have been called with the team's project key.
    mock_jira.list_recently_active_users.assert_awaited_once()
    call_kwargs = mock_jira.list_recently_active_users.call_args.kwargs
    assert call_kwargs.get("project_keys") == ["ENG"]


def test_member_suggestions_uses_first_jira_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When multiple connections exist, only the first Jira one is used."""
    gl_id = _make_gitlab_connection(session_factory)
    jira_id_1 = _make_jira_connection(session_factory)
    jira_id_2 = _make_jira_connection(session_factory)
    team_id = _make_team(
        session_factory,
        code_connection_id=gl_id,
        connection_ids=[jira_id_1, jira_id_2],
    )

    used_jira_ids: list[UUID] = []
    mock_jira = _make_mock_jira_connector(recently_active=[])
    mock_gitlab = _make_mock_gitlab_connector()

    def fake_instantiate(session: object, cid: UUID, factory: object) -> object:
        if cid in (jira_id_1, jira_id_2):
            used_jira_ids.append(cid)
            return mock_jira
        return mock_gitlab

    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", fake_instantiate)

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/member-suggestions")
    assert resp.status_code == 200
    # Only the first Jira connection was instantiated.
    assert jira_id_1 in used_jira_ids
    assert jira_id_2 not in used_jira_ids
