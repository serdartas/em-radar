# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.repositories.source_connections import create_source_connection
from em_radar_api.source_connections import ConnectorName, SourceConnectionCreate
from em_radar_api.tables import TeamProfileTable
from em_radar_core.connectors import ConnectorAuthError, GroupRef, MemberRef
from em_radar_core.models import WorkingMode


# ---------------------------------------------------------------------------
# Setup helpers (mirror test_gitlab_team_scope.py)
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


def _make_mock_group_connector(
    *,
    search_groups_return: list[GroupRef] | None = None,
    list_group_members_return: list[MemberRef] | None = None,
    raise_auth_error: bool = False,
) -> MagicMock:
    connector = MagicMock()
    connector.close = AsyncMock()
    if raise_auth_error:
        connector.search_groups = AsyncMock(side_effect=ConnectorAuthError("unauthorized"))
        connector.list_group_members = AsyncMock(side_effect=ConnectorAuthError("unauthorized"))
    else:
        connector.search_groups = AsyncMock(return_value=search_groups_return or [])
        connector.list_group_members = AsyncMock(return_value=list_group_members_return or [])
    return connector


# ---------------------------------------------------------------------------
# GET /teams/{id}/gitlab/group-search
# ---------------------------------------------------------------------------


def test_group_search_proxies_to_connector_and_maps_results(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_group_connector(
        search_groups_return=[
            GroupRef(provider_group_id="7", name="Frontend", full_path="acme/frontend"),
            GroupRef(provider_group_id="8", name="Backend", full_path="acme/backend"),
        ]
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-search?q=acme")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["provider_group_id"] == "7"
    assert data[0]["name"] == "Frontend"
    assert data[0]["full_path"] == "acme/frontend"
    assert data[1]["provider_group_id"] == "8"

    # Connector was called with the query and a capped limit.
    call_kwargs = mock_connector.search_groups.call_args
    assert call_kwargs.args[0] == "acme"
    mock_connector.close.assert_awaited_once()


def test_group_search_returns_empty_list_when_connector_returns_nothing(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_group_connector(search_groups_return=[])
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-search?q=noresults")
    assert resp.status_code == 200
    assert resp.json() == []


def test_group_search_returns_409_when_team_has_no_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    team_id = _make_team(session_factory, code_connection_id=None)
    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-search?q=any")
    assert resp.status_code == 409


def test_group_search_returns_404_for_unknown_team(api_client: TestClient) -> None:
    resp = api_client.get(f"/api/teams/{uuid4()}/gitlab/group-search?q=any")
    assert resp.status_code == 404


def test_group_search_returns_502_on_connector_auth_error(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_group_connector(raise_auth_error=True)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-search?q=any")
    assert resp.status_code == 502
    mock_connector.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /teams/{id}/gitlab/group-members
# ---------------------------------------------------------------------------


def test_group_members_proxies_to_connector_and_returns_member_search_results(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_group_connector(
        list_group_members_return=[
            MemberRef(
                provider_user_id="42",
                username="alice",
                display_name="Alice Smith",
                avatar_url=None,
            ),
            MemberRef(
                provider_user_id="43",
                username="bob",
                display_name="Bob Jones",
                avatar_url="https://example.com/avatar.png",
            ),
        ]
    )
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-members?group_id=7")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["provider_user_id"] == "42"
    assert data[0]["username"] == "alice"
    assert data[0]["display_name"] == "Alice Smith"
    assert data[0]["avatar_url"] is None
    assert data[1]["provider_user_id"] == "43"
    assert data[1]["avatar_url"] == "https://example.com/avatar.png"

    # Connector was called with the group_id.
    call_kwargs = mock_connector.list_group_members.call_args
    assert call_kwargs.args[0] == "7"
    mock_connector.close.assert_awaited_once()


def test_group_members_returns_empty_list_when_group_has_no_members(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_group_connector(list_group_members_return=[])
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-members?group_id=99")
    assert resp.status_code == 200
    assert resp.json() == []


def test_group_members_returns_409_when_team_has_no_connection(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    team_id = _make_team(session_factory, code_connection_id=None)
    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-members?group_id=7")
    assert resp.status_code == 409


def test_group_members_returns_404_for_unknown_team(api_client: TestClient) -> None:
    resp = api_client.get(f"/api/teams/{uuid4()}/gitlab/group-members?group_id=7")
    assert resp.status_code == 404


def test_group_members_returns_502_on_connector_auth_error(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_group_connector(raise_auth_error=True)
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-members?group_id=7")
    assert resp.status_code == 502
    mock_connector.close.assert_awaited_once()


def test_group_members_passes_group_path_to_connector(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    mock_connector = _make_mock_group_connector(list_group_members_return=[])
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: mock_connector,
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/group-members?group_id=acme%2Ffrontend")
    assert resp.status_code == 200
    call_kwargs = mock_connector.list_group_members.call_args
    assert call_kwargs.args[0] == "acme/frontend"
