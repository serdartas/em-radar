"""Partial-data handling (M5-08): typed connector errors produce a note; report still succeeds.

Tests cover:
- Code-source transient error → partial-data note + succeeded
- Board-source auth error → partial-data note + succeeded
- Rate-limited error variant
- Non-typed ConnectorError (ConnectorDataError) during fetch → still 502 (fatal)
- Clean run → no partial-data notes
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorAuthError,
    ConnectorDataError,
    ConnectorRateLimitedError,
    ConnectorTransientError,
    MergeRequestScope,
)
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    Repository,
    ScopeVerificationStatus,
    Source,
)

from em_radar_api.tables import TeamGitLabRepositoryTable
from test_source_connection_routes import (
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
    _run_report,
)

_REPO_ID = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _seed_gitlab_repo(
    session_factory: sessionmaker[Session],
    team_id: str,
    connection_id: str,
    gitlab_project_id: int = 1,
) -> None:
    """Insert a verified TeamGitLabRepositoryTable row so report scoping includes it."""
    now = datetime.now(UTC)
    with session_factory() as session:
        session.add(
            TeamGitLabRepositoryTable(
                team_profile_id=UUID(team_id),
                connection_id=UUID(connection_id),
                gitlab_project_id=gitlab_project_id,
                name="test-repo",
                path_with_namespace="group/test-repo",
                verification_status=ScopeVerificationStatus.VERIFIED,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# Fake connectors that simulate error conditions
# ---------------------------------------------------------------------------


class _FakeGitLabBase:
    name: ClassVar[str] = "gitlab"
    display_name: ClassVar[str] = "GitLab (test stub)"
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

    async def list_repositories(self) -> list[Repository]:
        return [
            Repository(
                id=_REPO_ID,
                source=Source.GITLAB,
                external_id="repo-1",
                name="my-repo",
                full_path="group/my-repo",
                default_branch="main",
            )
        ]


class _TransientGitLab(_FakeGitLabBase):
    async def fetch_mergerequests(
        self, scope: MergeRequestScope, window: EvaluationWindow
    ) -> AsyncIterator[MergeRequest]:
        raise ConnectorTransientError("GitLab is temporarily unavailable")
        yield  # make it an async generator


class _RateLimitedGitLab(_FakeGitLabBase):
    async def fetch_mergerequests(
        self, scope: MergeRequestScope, window: EvaluationWindow
    ) -> AsyncIterator[MergeRequest]:
        raise ConnectorRateLimitedError("GitLab rate limit exceeded")
        yield


class _FatalDataErrorGitLab(_FakeGitLabBase):
    async def fetch_mergerequests(
        self, scope: MergeRequestScope, window: EvaluationWindow
    ) -> AsyncIterator[MergeRequest]:
        raise ConnectorDataError("Unexpected payload shape")
        yield


class _FailingJiraTestConnector(JiraTestConnector):
    """Jira connector that raises ConnectorAuthError during workitem fetch."""

    async def fetch_workitems(self, scope, window):
        raise ConnectorAuthError("Jira token expired")
        return
        yield


def _create_gitlab_connection(api_client: TestClient) -> str:
    return api_client.post(
        "/api/connections",
        json={"name": "GitLab", "connector_name": "gitlab", "config": {}},
    ).json()["id"]


def _create_mr_signal(api_client: TestClient, name: str) -> str:
    """Create a merge-request signal definition and return its id."""
    return api_client.post(
        "/api/signal-definitions",
        json={
            "name": name,
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


def _create_group(api_client: TestClient, name: str, signal_ids: list[str]) -> str:
    """Create a signal-config group and return its id."""
    return api_client.post(
        "/api/signal-config-groups",
        json={"name": name, "signal_ids": signal_ids},
    ).json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_transient_code_source_error_produces_partial_data_note(
    api_client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ConnectorTransientError on code fetch → succeeded report with a code partial-data note.

    The signal group must contain a code signal so the fetch is not skipped by the source guard.
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _TransientGitLab],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    gitlab_id = _create_gitlab_connection(api_client)
    mr_signal = _create_mr_signal(api_client, "Transient-MR signal")
    group = _create_group(api_client, "Transient group", [mr_signal])
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Transient team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group],
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]
    _seed_gitlab_repo(session_factory, team_id, gitlab_id)

    report = _run_report(api_client, team_id)

    assert report["status"] == "succeeded"
    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    assert len(notes) == 1
    assert notes[0]["source"] == "code"
    assert "ConnectorTransientError" in notes[0]["reason"]


def test_rate_limited_code_source_produces_partial_data_note(
    api_client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ConnectorRateLimitedError on code fetch → succeeded report with a partial-data note.

    The signal group must contain a code signal so the fetch is not skipped by the source guard.
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _RateLimitedGitLab],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    gitlab_id = _create_gitlab_connection(api_client)
    mr_signal = _create_mr_signal(api_client, "Rate-limited MR signal")
    group = _create_group(api_client, "Rate-limited group", [mr_signal])
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Rate-limited team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group],
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]
    _seed_gitlab_repo(session_factory, team_id, gitlab_id)

    report = _run_report(api_client, team_id)

    assert report["status"] == "succeeded"
    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    assert any("code" == n["source"] for n in notes)


def test_non_typed_connector_error_is_still_fatal(
    api_client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ConnectorDataError (non-partial-data error) must yield 502, not a succeeded report.

    The signal group must contain a code signal so the fetch is not skipped by the source guard.
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _FatalDataErrorGitLab],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    gitlab_id = _create_gitlab_connection(api_client)
    mr_signal = _create_mr_signal(api_client, "Fatal error MR signal")
    group = _create_group(api_client, "Fatal error group", [mr_signal])
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Fatal error team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group],
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]
    _seed_gitlab_repo(session_factory, team_id, gitlab_id)

    job_resp = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )
    assert job_resp.status_code == 202
    job = api_client.get(f"/api/reports/jobs/{job_resp.json()['id']}").json()
    assert job["status"] == "failed", (
        "ConnectorDataError must cause job failure, not be swallowed into a partial-data note"
    )


def test_board_only_team_all_sources_failed_marks_report_failed(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AUDIT-5: board-only team whose sole board source fails → FAILED (not SUCCEEDED)."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FailingJiraTestConnector],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])

    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Board-only fail team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "working_mode": "kanban",
        },
    ).json()["id"]

    report = _run_report(api_client, team_id)

    assert report["status"] == "failed", (
        "board-only team with failing board source must be marked FAILED, not SUCCEEDED"
    )
    assert report["findings"] == []


def test_scrum_board_partial_workitem_failure_fails_gracefully(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sprint-window run whose workitem fetch fails after board metadata (incl. the sprint)
    succeeded must fail gracefully, not raise a FOREIGN KEY violation on the window insert."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FailingJiraTestConnector],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    team_id = _create_jira_team(api_client, jira_id, scope_id, "scrum", sprint_length_days=14)

    report = _run_report(api_client, team_id)

    assert report["status"] == "failed"
    assert report["findings"] == []


def test_code_only_team_all_sources_failed_marks_report_failed(
    api_client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AUDIT-5: code-only team whose sole (code) source fails → FAILED (not SUCCEEDED).

    The signal group must contain a code signal so the fetch is not skipped by the source guard.
    """
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_TransientGitLab],
    )
    gitlab_id = _create_gitlab_connection(api_client)
    mr_signal = _create_mr_signal(api_client, "Code-only fail MR signal")
    group = _create_group(api_client, "Code-only fail group", [mr_signal])
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Code-only fail team",
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group],
            "working_mode": "kanban",
        },
    ).json()["id"]
    _seed_gitlab_repo(session_factory, team_id, gitlab_id)

    report = _run_report(api_client, team_id)

    assert report["status"] == "failed", (
        "code-only team with failing code source must be marked FAILED, not SUCCEEDED"
    )
    assert report["findings"] == []


def test_no_partial_data_note_when_all_sources_succeed(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When all sources succeed, partial_data_notes must be empty."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    team_id = _create_jira_team(api_client, jira_id, scope_id, "scrum", sprint_length_days=14)

    report = _run_report(api_client, team_id)

    assert report["signal_pack_snapshot"].get("partial_data_notes", []) == []
