"""Tests for M3.4-05: report run requires at least one team source; skips signals for
missing sources.

Each test exercises one of the four source combinations:
  - no source   → 422
  - board only  → board signals run, code signals skipped
  - code only   → code signals run, board signals skipped
  - both        → all signals run, nothing skipped
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from fastapi.testclient import TestClient

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
    Source,
)

from test_source_connection_routes import (
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
)

_BOARD_CAPABILITIES = ["sprint", "statuses", "labels"]

_REPO_ID = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_MR_AUTHOR_ID = UUID("c3d4e5f6-a7b8-9012-cdef-123456789012")


class _FakeGitLabMRConnector:
    """Minimal GitLab connector that implements MergeRequestProvider. Used in tests only."""

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

    async def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        del scope, window
        yield MergeRequest(
            id=UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901"),
            source=Source.GITLAB,
            external_id="mr-1",
            repository_id=_REPO_ID,
            iid=1,
            title="Fix something",
            state=MergeRequestState.OPEN,
            author_id=_MR_AUTHOR_ID,
            target_branch="main",
            source_branch="fix-something",
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
            updated_at=datetime(2026, 7, 1, tzinfo=UTC),
        )


def _create_gitlab_connection(api_client: TestClient) -> str:
    return api_client.post(
        "/api/connections",
        json={"name": "GitLab", "connector_name": "gitlab", "config": {}},
    ).json()["id"]


def _create_wi_signal(api_client: TestClient, name: str) -> str:
    return api_client.post(
        "/api/signal-definitions",
        json={
            "name": name,
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "status_category", "operator": "is", "value": "in_progress"}
                ],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "enabled": True,
            "origin": "user_created",
        },
    ).json()["id"]


def _create_mr_signal(api_client: TestClient, name: str) -> str:
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
            "enabled": True,
            "origin": "user_created",
        },
    ).json()["id"]


def _create_group(api_client: TestClient, name: str, signal_ids: list[str]) -> str:
    return api_client.post(
        "/api/signal-config-groups",
        json={"name": name, "signal_ids": signal_ids},
    ).json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_source_returns_422(api_client: TestClient, monkeypatch) -> None:
    """A team with no board scope and no code_connection_id cannot run a report."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    connection_id = _create_jira_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={"name": "No source team", "connection_ids": [connection_id]},
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 422
    assert "no source" in response.json()["detail"]


def test_board_only_runs_wi_signals_skips_mr_signals(api_client: TestClient, monkeypatch) -> None:
    """Board-only team: work-item signals run; merge-request signals are skipped with a note."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    wi_signal = _create_wi_signal(api_client, "WI board-only")
    mr_signal = _create_mr_signal(api_client, "MR board-only")
    group = _create_group(api_client, "Mixed board-only group", [wi_signal, mr_signal])
    team_id = _create_jira_team(
        api_client,
        connection_id,
        scope_id,
        "scrum",
        sprint_length_days=14,
        group_ids=[group],
    )

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    snapshot = response.json()["signal_pack_snapshot"]
    skipped_ids = {s["id"] for s in snapshot["skipped_signals"]}

    assert mr_signal in skipped_ids, "MR signal should be skipped when no code source"
    assert wi_signal not in skipped_ids, "WI signal should not be skipped when board is present"

    skipped_mr = next(s for s in snapshot["skipped_signals"] if s["id"] == mr_signal)
    assert "code source" in skipped_mr["reason"]


def test_code_only_runs_mr_signals_skips_wi_signals(api_client: TestClient, monkeypatch) -> None:
    """Code-only team: merge-request signals run; work-item signals are skipped with a note."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_FakeGitLabMRConnector],
    )
    gitlab_id = _create_gitlab_connection(api_client)
    wi_signal = _create_wi_signal(api_client, "WI code-only")
    mr_signal = _create_mr_signal(api_client, "MR code-only")
    group = _create_group(api_client, "Mixed code-only group", [wi_signal, mr_signal])
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Code only team",
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group],
            "working_mode": "kanban",
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    snapshot = response.json()["signal_pack_snapshot"]
    skipped_ids = {s["id"] for s in snapshot["skipped_signals"]}

    assert wi_signal in skipped_ids, "WI signal should be skipped when no board source"
    assert mr_signal not in skipped_ids, "MR signal should not be skipped when code source present"

    skipped_wi = next(s for s in snapshot["skipped_signals"] if s["id"] == wi_signal)
    assert "board source" in skipped_wi["reason"]


def test_both_sources_no_signals_skipped(api_client: TestClient, monkeypatch) -> None:
    """Team with board + code sources: all signals run; nothing is skipped."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _FakeGitLabMRConnector],
    )
    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, _BOARD_CAPABILITIES)
    gitlab_id = _create_gitlab_connection(api_client)
    wi_signal = _create_wi_signal(api_client, "WI both")
    mr_signal = _create_mr_signal(api_client, "MR both")
    group = _create_group(api_client, "Mixed both group", [wi_signal, mr_signal])
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Both sources team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group],
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    snapshot = response.json()["signal_pack_snapshot"]
    assert snapshot["skipped_signals"] == [], (
        "No signals should be skipped when both sources present"
    )
