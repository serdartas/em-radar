"""Partial-data handling (M5-08): typed connector errors produce a note; report still succeeds.

Tests cover:
- Code-source transient error → partial-data note + succeeded
- Board-source auth error → partial-data note + succeeded
- Rate-limited error variant
- Non-typed ConnectorError (ConnectorDataError) during fetch → still 502 (fatal)
- All sources failing → report fails (not misleadingly "succeeded" with 0 data)
- Clean run → no partial-data notes
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

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
    Source,
)

from test_source_connection_routes import (
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
)

_REPO_ID = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_transient_code_source_error_produces_partial_data_note(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ConnectorTransientError on code fetch → succeeded report with a code partial-data note."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _TransientGitLab],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Transient team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "succeeded"
    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    assert len(notes) == 1
    assert notes[0]["source"] == "code"
    assert "ConnectorTransientError" in notes[0]["reason"]


def test_rate_limited_code_source_produces_partial_data_note(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ConnectorRateLimitedError on code fetch → succeeded report with a partial-data note."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _RateLimitedGitLab],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Rate-limited team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    notes = response.json()["signal_pack_snapshot"]["partial_data_notes"]
    assert any("code" == n["source"] for n in notes)


def test_non_typed_connector_error_is_still_fatal(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ConnectorDataError (non-partial-data error) must yield 502, not a succeeded report."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _FatalDataErrorGitLab],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])
    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Fatal error team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 502, (
        "ConnectorDataError must propagate as 502, not be swallowed into a partial-data note"
    )


def test_auth_error_on_board_source_produces_board_partial_data_note(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ConnectorAuthError during board fetch → succeeded report with a board partial-data note."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FailingJiraTestConnector],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, ["sprint", "statuses", "labels"])

    # Board-only team: only board source, no code connection.
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Board auth-error team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "working_mode": "kanban",
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "succeeded"
    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    assert len(notes) == 1
    assert notes[0]["source"] == "board"
    assert "ConnectorAuthError" in notes[0]["reason"]


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

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    assert response.json()["signal_pack_snapshot"].get("partial_data_notes", []) == []
