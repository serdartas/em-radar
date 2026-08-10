"""Tests for M3.5-05: report runner derives a concrete date-range window for MR fetch.

Three scenarios:
  - Scrum team with a code source: the SPRINT window is converted to a DATE_RANGE window
    (non-null start/end) before being handed to the code connector.
  - Sprint with no dates: the fallback 14-day lookback window is used for both bounds.
  - Code-only / kanban team: the DATE_RANGE window passes through unchanged.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from em_radar_core.connectors import Capabilities, ConnectionTestResult, MergeRequestScope
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    Repository,
    Source,
    Sprint,
    SprintState,
    WindowType,
)

from test_source_connection_routes import (
    FrozenReportDateTime,
    JiraTestConnector,
    _REPORT_STARTED_AT,
    _create_board_scope,
    _create_jira_connection,
)

_BOARD_CAPABILITIES = ["sprint", "statuses", "labels"]

_SPRINT_START = datetime(2026, 6, 1, tzinfo=UTC)
_SPRINT_END = datetime(2026, 6, 14, tzinfo=UTC)

_REPO_ID = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
_MR_AUTHOR_ID = UUID("c3d4e5f6-a7b8-9012-cdef-123456789012")


class _JiraWithDatedSprintConnector(JiraTestConnector):
    """Jira fake whose active sprint carries concrete start/end dates."""

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        assert board_id == "20000"
        return [
            Sprint(
                id="45cdfd02-9cde-4c65-a618-7728fc9fb495",
                source=Source.JIRA,
                external_id="30000",
                board_id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                name="Platform Sprint 12",
                state=SprintState.ACTIVE,
                start_date=_SPRINT_START,
                end_date=_SPRINT_END,
            )
        ]


class _JiraWithUndatedSprintConnector(JiraTestConnector):
    """Jira fake whose active sprint has no start_date or end_date."""

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        assert board_id == "20000"
        return [
            Sprint(
                id="45cdfd02-9cde-4c65-a618-7728fc9fb495",
                source=Source.JIRA,
                external_id="30000",
                board_id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                name="Platform Sprint 12",
                state=SprintState.ACTIVE,
            )
        ]


class _RecordingMRConnector:
    """GitLab fake that records every window it receives from fetch_mergerequests."""

    name: ClassVar[str] = "gitlab"
    display_name: ClassVar[str] = "GitLab (recording)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    min_model_version: ClassVar[int] = 1

    received_windows: ClassVar[list[EvaluationWindow]] = []

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
        _RecordingMRConnector.received_windows.append(window)
        if False:
            yield  # make this an async generator without yielding any MRs


@pytest.fixture(autouse=True)
def _clear_recording() -> None:
    _RecordingMRConnector.received_windows.clear()


def _create_gitlab_connection(api_client: TestClient) -> str:
    return api_client.post(
        "/api/connections",
        json={"name": "GitLab", "connector_name": "gitlab", "config": {}},
    ).json()["id"]


def test_scrum_sprint_window_is_converted_to_date_range_for_mr_fetch(
    api_client: TestClient, monkeypatch
) -> None:
    """SPRINT window → DATE_RANGE with sprint's start_date/end_date passed to MR provider."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_JiraWithDatedSprintConnector, _RecordingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, _BOARD_CAPABILITIES)
    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Scrum with code",
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
    assert len(_RecordingMRConnector.received_windows) == 1
    mr_window = _RecordingMRConnector.received_windows[0]
    assert mr_window.window_type == WindowType.DATE_RANGE
    assert mr_window.start is not None
    assert mr_window.end is not None
    assert mr_window.start == _SPRINT_START
    assert mr_window.end == _SPRINT_END


def test_sprint_without_dates_uses_fallback_lookback_window(
    api_client: TestClient, monkeypatch
) -> None:
    """Sprint with no start_date/end_date → fallback 14-day lookback for both bounds."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_JiraWithUndatedSprintConnector, _RecordingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, _BOARD_CAPABILITIES)
    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Scrum undated sprint",
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
    assert len(_RecordingMRConnector.received_windows) == 1
    mr_window = _RecordingMRConnector.received_windows[0]
    assert mr_window.window_type == WindowType.DATE_RANGE
    assert mr_window.start == _REPORT_STARTED_AT - timedelta(days=14)
    assert mr_window.end == _REPORT_STARTED_AT


def test_date_range_window_passes_through_unchanged_to_mr_fetch(
    api_client: TestClient, monkeypatch
) -> None:
    """DATE_RANGE window (kanban / code-only) is forwarded to the MR provider as-is."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_RecordingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Code only kanban",
            "code_connection_id": gitlab_id,
            "working_mode": "kanban",
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    assert len(_RecordingMRConnector.received_windows) == 1
    mr_window = _RecordingMRConnector.received_windows[0]
    assert mr_window.window_type == WindowType.DATE_RANGE
    assert mr_window.start == _REPORT_STARTED_AT - timedelta(days=14)
    assert mr_window.end == _REPORT_STARTED_AT
