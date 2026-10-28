# SPDX-License-Identifier: Apache-2.0
"""M9-17: Provider-agnostic team code-scope abstraction.

A fake connector that is NOT the GitLab connector implements MemberProvider,
RepositorySearchProvider, RepositoryActivityProvider, and UserIdentityProvider.
The report runner and member/repository endpoints exercise the same code paths
through the abstraction without any provider-specific branching, proving that
a future GitHub (or any other) connector can plug in unchanged.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar
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
from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    MemberRef,
    MergeRequestScope,
    RepositoryActivity,
    RepositoryRef,
)
from em_radar_core.models import ScopeVerificationStatus, WorkingMode


# ---------------------------------------------------------------------------
# Fake second connector (not GitLab)
# ---------------------------------------------------------------------------


class _FakeConnector:
    """Minimal fake connector that is not GitLab.

    Uses provider_user_id strings that are not numeric integers ("gh_user_abc")
    to prove the abstraction is not tied to GitLab's integer ID space.
    """

    name: ClassVar[str] = "gitlab"  # registered as gitlab to pass capability validation
    display_name: ClassVar[str] = "Fake Connector (provider-agnostic test)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    min_model_version: ClassVar[int] = 1

    MEMBER_A = MemberRef(provider_user_id="gh_user_abc", username="alice", display_name="Alice")
    MEMBER_B = MemberRef(provider_user_id="gh_user_xyz", username="bob", display_name="Bob")
    REPO_1 = RepositoryRef(
        provider_project_id="MDEwOlJlcG9zaXRvcnkxMjM=",
        name="acme-backend",
        path_with_namespace="acme/acme-backend",
    )

    def __init__(self, config: dict[str, object]) -> None:
        pass

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="ok")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        return Capabilities(provides_mergerequests=True, provides_repositories=True)

    async def close(self) -> None:
        pass

    # MemberProvider
    async def search_users(self, query: str, *, limit: int) -> list[MemberRef]:
        return [self.MEMBER_A, self.MEMBER_B]

    async def get_user(self, provider_user_id: str) -> MemberRef | None:
        mapping = {m.provider_user_id: m for m in [self.MEMBER_A, self.MEMBER_B]}
        return mapping.get(provider_user_id)

    # RepositorySearchProvider
    async def search_projects(self, query: str, *, limit: int) -> list[RepositoryRef]:
        return [self.REPO_1]

    async def get_project(self, provider_project_id: str) -> RepositoryRef | None:
        if provider_project_id == self.REPO_1.provider_project_id:
            return self.REPO_1
        return None

    # RepositoryActivityProvider
    async def discover_repositories_by_activity(
        self,
        member_provider_user_ids: list[str],
        *,
        since: datetime,
        limit: int,
    ) -> list[RepositoryActivity]:
        return [
            RepositoryActivity(
                provider_project_id=self.REPO_1.provider_project_id,
                name=self.REPO_1.name,
                path_with_namespace=self.REPO_1.path_with_namespace,
                contributing_member_count=len(member_provider_user_ids),
                merge_request_count=3,
                last_activity_at=since,
            )
        ]

    # list_repositories stub (required by ConnectorBase shape)
    async def list_repositories(self) -> list:
        return []

    async def fetch_mergerequests(self, scope: MergeRequestScope, window) -> AsyncIterator:  # type: ignore[override]
        return
        yield  # make it an async generator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gitlab_connection(session_factory: sessionmaker[Session]) -> UUID:
    with session_factory() as session:
        conn = create_source_connection(
            session,
            SourceConnectionCreate(
                name=f"Code {uuid4().hex[:8]}",
                connector_name=ConnectorName.GITLAB,
            ),
        )
    return conn.id


def _make_team(
    session_factory: sessionmaker[Session],
    code_connection_id: UUID,
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
    connection_id: UUID,
    provider_user_id: str,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabMemberTable(
                team_profile_id=team_id,
                connection_id=connection_id,
                provider_user_id=provider_user_id,
                username="user",
                display_name=None,
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def _seed_repo(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    connection_id: UUID,
    provider_project_id: str,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabRepositoryTable(
                team_profile_id=team_id,
                connection_id=connection_id,
                provider_project_id=provider_project_id,
                name="repo",
                path_with_namespace="acme/repo",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_put_members_with_non_numeric_provider_user_id(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT /members accepts and stores opaque (non-integer) provider_user_id strings.

    Proves the endpoint is not limited to GitLab's numeric ID space.
    """
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    fake = _FakeConnector({})
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: fake,
    )

    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/members",
        json=[{"provider_user_id": _FakeConnector.MEMBER_A.provider_user_id}],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["provider_user_id"] == "gh_user_abc"
    assert data[0]["username"] == "alice"


def test_put_repositories_with_opaque_provider_project_id(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT /repositories accepts and stores opaque (non-integer) provider_project_id strings."""
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)

    fake = _FakeConnector({})
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: fake,
    )

    pid = _FakeConnector.REPO_1.provider_project_id
    resp = api_client.put(
        f"/api/teams/{team_id}/gitlab/repositories",
        json=[{"provider_project_id": pid}],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["provider_project_id"] == pid


def test_verify_config_works_with_non_gitlab_connector(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """verify-config re-resolves opaque provider_user_id strings through any MemberProvider.

    No GitLab-specific branching in the verification path.
    """
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id, "gh_user_abc")
    _seed_repo(session_factory, team_id, conn_id, "MDEwOlJlcG9zaXRvcnkxMjM=")

    fake = _FakeConnector({})
    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: fake,
    )

    resp = api_client.post(f"/api/teams/{team_id}/gitlab/verify-config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["members"][0]["verification_status"] == "verified"
    assert data["members"][0]["provider_user_id"] == "gh_user_abc"
    assert data["repositories"][0]["verification_status"] == "verified"
    assert data["repositories"][0]["provider_project_id"] == "MDEwOlJlcG9zaXRvcnkxMjM="


def test_repository_suggestions_passes_opaque_ids_to_connector(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """repository-suggestions passes stored provider_user_id strings verbatim to the connector.

    The connector receives 'gh_user_abc' (not some int conversion), proving provider-neutrality.
    """
    conn_id = _make_gitlab_connection(session_factory)
    team_id = _make_team(session_factory, code_connection_id=conn_id)
    _seed_member(session_factory, team_id, conn_id, "gh_user_abc")

    received_ids: list[list[str]] = []

    class _SpyConnector(_FakeConnector):
        async def discover_repositories_by_activity(
            self,
            member_provider_user_ids: list[str],
            *,
            since: datetime,
            limit: int,
        ) -> list[RepositoryActivity]:
            received_ids.append(list(member_provider_user_ids))
            return await super().discover_repositories_by_activity(
                member_provider_user_ids, since=since, limit=limit
            )

    monkeypatch.setattr(
        "em_radar_api.routers.teams.instantiate_connector",
        lambda *_a, **_kw: _SpyConnector({}),
    )

    resp = api_client.get(f"/api/teams/{team_id}/gitlab/repository-suggestions")
    assert resp.status_code == 200
    # The stored provider_user_id was passed through verbatim — no int conversion.
    assert len(received_ids) >= 1
    assert received_ids[0] == ["gh_user_abc"]
