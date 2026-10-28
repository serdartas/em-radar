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
from em_radar_api.tables import (
    TeamGitLabMemberTable,
    TeamGitLabRepositoryTable,
    TeamProfileTable,
)
from em_radar_core.connectors import ConnectorError, MemberRef, RepositoryRef
from em_radar_core.models import ScopeVerificationStatus, WorkingMode


# ---------------------------------------------------------------------------
# Setup helpers (mirrors test_gitlab_team_scope.py)
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


def _seed_member(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    connection_id: UUID | None,
    provider_user_id: str = "10",
    username: str = "dev",
    display_name: str = "Dev User",
    status: ScopeVerificationStatus = ScopeVerificationStatus.VERIFIED,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        row = TeamGitLabMemberTable(
            team_profile_id=team_id,
            connection_id=connection_id,
            provider_user_id=provider_user_id,
            username=username,
            display_name=display_name,
            verification_status=status,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()


def _seed_repo(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    connection_id: UUID | None,
    provider_project_id: str = "5",
    name: str = "myrepo",
    path_with_namespace: str = "group/myrepo",
    status: ScopeVerificationStatus = ScopeVerificationStatus.VERIFIED,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        row = TeamGitLabRepositoryTable(
            team_profile_id=team_id,
            connection_id=connection_id,
            provider_project_id=provider_project_id,
            name=name,
            path_with_namespace=path_with_namespace,
            verification_status=status,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()


def _make_mock_connector(
    *,
    get_user_return: MemberRef | None = None,
    get_project_return: RepositoryRef | None = None,
    raise_error: bool = False,
) -> MagicMock:
    connector = MagicMock()
    connector.close = AsyncMock()
    if raise_error:
        connector.get_user = AsyncMock(side_effect=ConnectorError("transient"))
        connector.get_project = AsyncMock(side_effect=ConnectorError("transient"))
        connector.search_users = AsyncMock(side_effect=ConnectorError("transient"))
        connector.search_projects = AsyncMock(side_effect=ConnectorError("transient"))
    else:
        connector.get_user = AsyncMock(return_value=get_user_return)
        connector.get_project = AsyncMock(return_value=get_project_return)
        connector.search_users = AsyncMock(return_value=[])
        connector.search_projects = AsyncMock(return_value=[])
    return connector


# ---------------------------------------------------------------------------
# verify-config: deleted user → UNAVAILABLE, row preserved
# ---------------------------------------------------------------------------


def test_verify_config_marks_deleted_user_unavailable(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id, provider_user_id="10")

    # Connector returns None → user deleted on GitLab side.
    mock = _make_mock_connector(get_user_return=None)
    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", lambda *_a, **_kw: mock)

    resp = api_client.post(f"/api/teams/{team_id}/gitlab/verify-config")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["members"]) == 1
    assert data["members"][0]["verification_status"] == "unavailable"
    assert data["members"][0]["provider_user_id"] == "10"  # row preserved


def test_verify_config_marks_archived_repo_unavailable(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_repo(session_factory, team_id, conn_id, provider_project_id="5")

    # Connector returns an archived repo → should be marked UNAVAILABLE.
    mock = _make_mock_connector(
        get_project_return=RepositoryRef(
            provider_project_id="5",
            name="myrepo",
            path_with_namespace="group/myrepo",
            is_archived=True,
        )
    )
    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", lambda *_a, **_kw: mock)

    resp = api_client.post(f"/api/teams/{team_id}/gitlab/verify-config")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["repositories"]) == 1
    assert data["repositories"][0]["verification_status"] == "unavailable"
    assert data["repositories"][0]["provider_project_id"] == "5"  # row preserved


def test_verify_config_refreshes_renamed_entity(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id, provider_user_id="10", username="oldname")

    # Connector returns the same id but with a new username → renamed, still VERIFIED.
    mock = _make_mock_connector(
        get_user_return=MemberRef(
            provider_user_id="10", username="newname", display_name="New Name"
        )
    )
    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", lambda *_a, **_kw: mock)

    resp = api_client.post(f"/api/teams/{team_id}/gitlab/verify-config")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["members"]) == 1
    member = data["members"][0]
    assert member["verification_status"] == "verified"
    assert member["username"] == "newname"
    assert member["display_name"] == "New Name"


def test_verify_config_marks_different_instance_unverified(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    other_conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    # Member was seeded with a DIFFERENT connection_id (other instance).
    _seed_member(session_factory, team_id, other_conn_id, provider_user_id="99")
    _seed_repo(session_factory, team_id, other_conn_id, provider_project_id="88")

    mock = _make_mock_connector()
    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", lambda *_a, **_kw: mock)

    resp = api_client.post(f"/api/teams/{team_id}/gitlab/verify-config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["members"][0]["verification_status"] == "unverified"
    assert data["repositories"][0]["verification_status"] == "unverified"
    # Connector was never queried for mismatched-instance rows.
    mock.get_user.assert_not_called()
    mock.get_project.assert_not_called()


def test_verify_config_transient_error_leaves_status_unchanged(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(
        session_factory,
        team_id,
        conn_id,
        provider_user_id="10",
        status=ScopeVerificationStatus.VERIFIED,
    )

    # Connector raises a transient error → status must stay VERIFIED (not flipped).
    mock = _make_mock_connector(raise_error=True)
    monkeypatch.setattr("em_radar_api.routers.teams.instantiate_connector", lambda *_a, **_kw: mock)

    resp = api_client.post(f"/api/teams/{team_id}/gitlab/verify-config")
    assert resp.status_code == 200
    assert resp.json()["members"][0]["verification_status"] == "verified"


def test_verify_config_returns_404_for_unknown_team(api_client: TestClient) -> None:
    resp = api_client.post(f"/api/teams/{uuid4()}/gitlab/verify-config")
    assert resp.status_code == 404


def test_verify_config_connector_instantiation_failure_only_updates_mismatched_rows(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the connector cannot be instantiated, same-connection rows stay unchanged.

    Only entries whose connection_id diverges from the current code_connection_id
    should be flipped to UNVERIFIED — the same-connection rows must not be touched.
    """
    conn_id = _make_gitlab_connection(session_factory)
    other_conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    # A verified member on the active connection — must stay VERIFIED.
    _seed_member(
        session_factory,
        team_id,
        conn_id,
        provider_user_id="10",
        status=ScopeVerificationStatus.VERIFIED,
    )
    # A member from a stale (different) connection — must flip to UNVERIFIED.
    _seed_member(
        session_factory,
        team_id,
        other_conn_id,
        provider_user_id="99",
        status=ScopeVerificationStatus.VERIFIED,
    )

    # Simulate a connector config error so _require_gitlab_connector raises HTTPException.
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            __import__("fastapi").HTTPException(status_code=422, detail="bad config")
        ),
    )

    resp = api_client.post(f"/api/teams/{team_id}/gitlab/verify-config")
    assert resp.status_code == 200
    data = resp.json()
    by_id = {m["provider_user_id"]: m for m in data["members"]}
    assert by_id["10"]["verification_status"] == "verified"  # unchanged
    assert by_id["99"]["verification_status"] == "unverified"  # different instance → UNVERIFIED


# ---------------------------------------------------------------------------
# Per-item delete endpoints
# ---------------------------------------------------------------------------


def test_delete_gitlab_member_removes_exactly_one_row(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id, provider_user_id="10")
    _seed_member(session_factory, team_id, conn_id, provider_user_id="20")

    # Fetch both rows to get their ids.
    members = api_client.get(f"/api/teams/{team_id}/gitlab/members").json()
    assert len(members) == 2
    target_id = next(m["id"] for m in members if m["provider_user_id"] == "10")

    resp = api_client.delete(f"/api/teams/{team_id}/gitlab/members/{target_id}")
    assert resp.status_code == 204

    remaining = api_client.get(f"/api/teams/{team_id}/gitlab/members").json()
    assert len(remaining) == 1
    assert remaining[0]["provider_user_id"] == "20"  # untouched


def test_delete_gitlab_repository_removes_exactly_one_row(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_repo(session_factory, team_id, conn_id, provider_project_id="5")
    _seed_repo(session_factory, team_id, conn_id, provider_project_id="6")

    repos = api_client.get(f"/api/teams/{team_id}/gitlab/repositories").json()
    assert len(repos) == 2
    target_id = next(r["id"] for r in repos if r["provider_project_id"] == "5")

    resp = api_client.delete(f"/api/teams/{team_id}/gitlab/repositories/{target_id}")
    assert resp.status_code == 204

    remaining = api_client.get(f"/api/teams/{team_id}/gitlab/repositories").json()
    assert len(remaining) == 1
    assert remaining[0]["provider_project_id"] == "6"  # untouched


def test_delete_gitlab_member_returns_404_for_wrong_team(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    other_team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id, provider_user_id="10")

    members = api_client.get(f"/api/teams/{team_id}/gitlab/members").json()
    member_id = members[0]["id"]

    # Attempting to delete with the wrong team_id must 404.
    resp = api_client.delete(f"/api/teams/{other_team_id}/gitlab/members/{member_id}")
    assert resp.status_code == 404
