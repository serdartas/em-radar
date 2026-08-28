# SPDX-License-Identifier: Apache-2.0
"""M9-06: Report runner scopes MR fetch to team-owned repositories.

Three scenarios:
  - Team with configured repositories: fetch_mergerequests receives a MergeRequestScope whose
    repository_external_ids match exactly the configured ids; a connector-visible but unconfigured
    repo is not included in the scope.
  - Team with code signals but no configured repositories: code evaluation is skipped, a
    non-blocking note is recorded, and the report status is SUCCEEDED (not FAILED).
  - Code finding scope label: findings produced by code signals carry scope_name equal to the
    team-owned repository scope label.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID, uuid5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    MergeRequestScope,
)
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    Repository,
    ScopeVerificationStatus,
    Source,
)

from em_radar_api.tables import TeamGitLabRepositoryTable
from test_source_connection_routes import (
    FrozenReportDateTime,
    _REPORT_STARTED_AT,
    _run_report,
)

# Stable UUIDs for connector-returned objects.
_CONFIGURED_REPO_ID = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_UNCONFIGURED_REPO_ID = UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")
_MR_AUTHOR_ID = UUID("c3d4e5f6-a7b8-9012-cdef-123456789012")

# The two simulated GitLab project ids exposed by the connector.
_CONFIGURED_PROJECT_ID = 10  # added to team config
_UNCONFIGURED_PROJECT_ID = 20  # visible but NOT in team config


class _ScopingMRConnector:
    """GitLab fake that exposes two repositories and records the MergeRequestScope it receives.

    fetch_mergerequests yields one open MR belonging to the configured repository so that
    scope-name assertions can inspect an actual finding.
    """

    name: ClassVar[str] = "gitlab"
    display_name: ClassVar[str] = "GitLab (scoping test)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    min_model_version: ClassVar[int] = 1

    received_scopes: ClassVar[list[MergeRequestScope]] = []

    def __init__(self, config: dict[str, object]) -> None:
        pass

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="ok")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        return Capabilities(provides_mergerequests=True, provides_repositories=True)

    async def close(self) -> None:
        pass

    async def list_repositories(self) -> list[Repository]:
        return [
            Repository(
                id=_CONFIGURED_REPO_ID,
                source=Source.GITLAB,
                external_id=str(_CONFIGURED_PROJECT_ID),
                name="configured-repo",
                full_path="org/configured-repo",
                default_branch="main",
            ),
            Repository(
                id=_UNCONFIGURED_REPO_ID,
                source=Source.GITLAB,
                external_id=str(_UNCONFIGURED_PROJECT_ID),
                name="other-repo",
                full_path="org/other-repo",
                default_branch="main",
            ),
        ]

    async def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        _ScopingMRConnector.received_scopes.append(scope)
        yield MergeRequest(
            id=UUID("d4e5f6a7-b8c9-0123-def4-56789abcdef0"),
            source=Source.GITLAB,
            external_id="mr-42",
            repository_id=_CONFIGURED_REPO_ID,
            iid=42,
            title="Scoped MR",
            state=MergeRequestState.OPEN,
            author_id=_MR_AUTHOR_ID,
            target_branch="main",
            source_branch="feature/scoped",
            created_at=_REPORT_STARTED_AT,
            updated_at=_REPORT_STARTED_AT,
        )


_NAMESPACE = UUID("00000000-0000-0000-0000-0000000000aa")


def _namespaced_repository_id(external_id: str) -> UUID:
    return uuid5(_NAMESPACE, f"repository:{external_id}")


class _NamespacedMRConnector:
    """Fake mirroring the real GitLab connector's ``{host}/{id}`` external-id scheme.

    ``list_repositories`` returns a namespaced external id and derives the Repository primary
    key from it; ``fetch_mergerequests`` derives each MR's ``repository_id`` from the scope entry
    it receives (as the real connector does). The MR only links to a persisted Repository when
    the report scopes by the connector's external id rather than the bare numeric id.
    """

    name: ClassVar[str] = "gitlab"
    display_name: ClassVar[str] = "GitLab (namespaced test)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    min_model_version: ClassVar[int] = 1

    _external_id: ClassVar[str] = f"gitlab.example.com/{_CONFIGURED_PROJECT_ID}"

    def __init__(self, config: dict[str, object]) -> None:
        pass

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="ok")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        return Capabilities(provides_mergerequests=True, provides_repositories=True)

    async def close(self) -> None:
        pass

    async def list_repositories(self) -> list[Repository]:
        return [
            Repository(
                id=_namespaced_repository_id(self._external_id),
                source=Source.GITLAB,
                external_id=self._external_id,
                name="configured-repo",
                full_path="org/configured-repo",
                default_branch="main",
            )
        ]

    async def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        for external_id in scope.repository_external_ids:
            yield MergeRequest(
                id=uuid5(_NAMESPACE, f"mergerequest:{external_id}"),
                source=Source.GITLAB,
                external_id=f"{external_id}/mr-42",
                repository_id=_namespaced_repository_id(external_id),
                iid=42,
                title="Namespaced MR",
                state=MergeRequestState.OPEN,
                author_id=_MR_AUTHOR_ID,
                target_branch="main",
                source_branch="feature/scoped",
                created_at=_REPORT_STARTED_AT,
                updated_at=_REPORT_STARTED_AT,
            )


@pytest.fixture(autouse=True)
def _clear_scopes() -> None:
    _ScopingMRConnector.received_scopes.clear()


def _create_gitlab_connection(api_client: TestClient) -> str:
    return api_client.post(
        "/api/connections",
        json={"name": "GitLab scope test", "connector_name": "gitlab", "config": {}},
    ).json()["id"]


def _seed_gitlab_repo(
    session_factory: sessionmaker[Session],
    team_id: str,
    connection_id: str,
    gitlab_project_id: int,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabRepositoryTable(
                team_profile_id=UUID(team_id),
                connection_id=UUID(connection_id),
                gitlab_project_id=gitlab_project_id,
                name="configured-repo",
                path_with_namespace="org/configured-repo",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def _create_mr_signal_group(api_client: TestClient) -> str:
    signal_id = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Open MR scope test",
            "entity_type": "merge_request",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [{"field": "state", "operator": "is", "value": "open"}],
            },
            "report_settings": {"severity": "info", "category": "code"},
            "origin": "user_created",
        },
    ).json()["id"]
    return api_client.post(
        "/api/signal-config-groups",
        json={"name": "Scope test MR group", "signal_ids": [signal_id]},
    ).json()["id"]


def test_fetch_mergerequests_scoped_to_configured_repositories(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch_mergerequests receives a scope containing only the team's configured project id.

    The connector exposes two repositories (_CONFIGURED_PROJECT_ID and _UNCONFIGURED_PROJECT_ID).
    Only _CONFIGURED_PROJECT_ID is added to the team config, so the MergeRequestScope must
    contain exactly ["10"] — not ["10", "20"].
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_ScopingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    gitlab_id = _create_gitlab_connection(api_client)
    group_id = _create_mr_signal_group(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Scoped repo team",
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group_id],
            "working_mode": "kanban",
        },
    ).json()["id"]
    _seed_gitlab_repo(session_factory, team_id, gitlab_id, _CONFIGURED_PROJECT_ID)

    report = _run_report(api_client, team_id)

    assert report["status"] == "succeeded"

    assert len(_ScopingMRConnector.received_scopes) == 1, (
        "fetch_mergerequests must be called exactly once"
    )
    scope = _ScopingMRConnector.received_scopes[0]
    assert scope.repository_external_ids == [str(_CONFIGURED_PROJECT_ID)], (
        f"scope must contain only the configured project id; got {scope.repository_external_ids}"
    )
    assert str(_UNCONFIGURED_PROJECT_ID) not in scope.repository_external_ids, (
        "connector-visible but unconfigured project must not appear in the scope"
    )


def test_no_configured_repositories_skips_code_with_non_blocking_note(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code-only team with MR signals but zero configured repositories: report SUCCEEDS.

    The code fetch must be skipped entirely (connector is never called) and a non-blocking
    partial-data note with source='code' must be recorded. The report must not be marked FAILED.
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_ScopingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    gitlab_id = _create_gitlab_connection(api_client)
    group_id = _create_mr_signal_group(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "No repos team",
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group_id],
            "working_mode": "kanban",
        },
    ).json()["id"]
    # Deliberately do NOT seed any TeamGitLabRepositoryTable rows.

    report = _run_report(api_client, team_id)

    assert report["status"] == "succeeded", (
        "report must succeed even when no repositories are configured; got "
        f"status={report['status']!r}"
    )
    assert _ScopingMRConnector.received_scopes == [], (
        "connector fetch_mergerequests must not be called when no repos are configured"
    )
    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    code_notes = [n for n in notes if n["source"] == "code"]
    assert len(code_notes) == 1, f"expected exactly one code partial-data note; got {code_notes}"
    assert "no team-owned repositories configured" in code_notes[0]["reason"]


def test_scope_uses_connector_external_id_so_mr_links_to_repository(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The MR fetched for a configured repo must link to the persisted Repository.

    With a connector that namespaces external ids as ``{host}/{id}`` and derives each MR's
    repository_id from the scope entry, scoping by the bare numeric id would produce an MR whose
    repository_id does not match any persisted Repository (FK break / dropped MR / failed report).
    Scoping by the connector's external id keeps the linkage intact, so the MR finding appears.
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_NamespacedMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    gitlab_id = _create_gitlab_connection(api_client)
    group_id = _create_mr_signal_group(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Namespaced repo team",
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group_id],
            "working_mode": "kanban",
        },
    ).json()["id"]
    _seed_gitlab_repo(session_factory, team_id, gitlab_id, _CONFIGURED_PROJECT_ID)

    report = _run_report(api_client, team_id)

    assert report["status"] == "succeeded"
    mr_findings = [f for f in report["findings"] if f["entity_type"] == "mergerequest"]
    assert len(mr_findings) > 0, (
        "the MR must persist and link to its Repository so a finding is produced"
    )


def test_code_findings_carry_team_owned_scope_label(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code findings produced by MR signals include scope_name == 'MRs in team-owned repositories'."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_ScopingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    gitlab_id = _create_gitlab_connection(api_client)
    group_id = _create_mr_signal_group(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Scope label team",
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group_id],
            "working_mode": "kanban",
        },
    ).json()["id"]
    _seed_gitlab_repo(session_factory, team_id, gitlab_id, _CONFIGURED_PROJECT_ID)

    report = _run_report(api_client, team_id)

    assert report["status"] == "succeeded"
    mr_findings = [f for f in report["findings"] if f["entity_type"] == "mergerequest"]
    assert len(mr_findings) > 0, "expected at least one MR finding from the open MR"
    for finding in mr_findings:
        assert finding["scope_name"] == "MRs in team-owned repositories", (
            f"expected scope_name='MRs in team-owned repositories'; got {finding['scope_name']!r}"
        )
