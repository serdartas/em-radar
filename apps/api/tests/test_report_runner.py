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
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_core.connectors import Capabilities, ConnectionTestResult, MergeRequestScope
from em_radar_core.models import (
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    Repository,
    Source,
    Sprint,
    SprintState,
    WindowType,
)

from em_radar_api.tables import MergeRequestTable, WorkItemTable
from test_source_connection_routes import (
    FrozenReportDateTime,
    JiraTestConnector,
    _REPORT_STARTED_AT,
    _create_board_scope,
    _create_jira_connection,
    _run_report,
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

    _run_report(api_client, team_id)

    assert len(_RecordingMRConnector.received_windows) == 1
    mr_window = _RecordingMRConnector.received_windows[0]
    assert mr_window.window_type == WindowType.DATE_RANGE
    assert mr_window.start is not None
    assert mr_window.end is not None
    assert mr_window.start == _SPRINT_START
    assert mr_window.end == _REPORT_STARTED_AT


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

    _run_report(api_client, team_id)

    assert len(_RecordingMRConnector.received_windows) == 1
    mr_window = _RecordingMRConnector.received_windows[0]
    assert mr_window.window_type == WindowType.DATE_RANGE
    assert mr_window.start == _REPORT_STARTED_AT - timedelta(days=14)
    assert mr_window.end == _REPORT_STARTED_AT


class _LinkingMRConnector(_RecordingMRConnector):
    """GitLab fake that yields one MR referencing a matched and an unmatched work-item key."""

    display_name: ClassVar[str] = "GitLab (linking)"

    async def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        _LinkingMRConnector.received_windows.append(window)
        yield MergeRequest(
            id=UUID("d4e5f6a7-b8c9-0123-def4-56789abcdef0"),
            source=Source.GITLAB,
            external_id="mr-1",
            repository_id=_REPO_ID,
            iid=1,
            title="Implement PLAT-1 endpoint",
            description="Follow-up to NOPE-9 which has no matching work item.",
            state=MergeRequestState.OPEN,
            author_id=_MR_AUTHOR_ID,
            target_branch="main",
            source_branch="feature/plat-1",
            created_at=_REPORT_STARTED_AT,
            updated_at=_REPORT_STARTED_AT,
        )


def test_report_run_populates_merge_request_workitem_links(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    """A fetched MR referencing a fetched Jira work item persists resolved keys and ids;
    a referenced key with no matching work item stays in keys but resolves to no id."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _LinkingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, _BOARD_CAPABILITIES)
    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Scrum with linking code",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    _run_report(api_client, team_id)

    with session_factory() as session:
        workitem = session.exec(select(WorkItemTable).where(WorkItemTable.key == "PLAT-1")).one()
        merge_request = session.exec(select(MergeRequestTable)).one()

    assert "PLAT-1" in merge_request.linked_workitem_keys
    assert "NOPE-9" in merge_request.linked_workitem_keys
    assert workitem.id in merge_request.linked_workitem_ids
    # The unmatched key resolves to no id, so only the single matched id is stored.
    assert merge_request.linked_workitem_ids == [workitem.id]


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

    _run_report(api_client, team_id)

    assert len(_RecordingMRConnector.received_windows) == 1
    mr_window = _RecordingMRConnector.received_windows[0]
    assert mr_window.window_type == WindowType.DATE_RANGE
    assert mr_window.start == _REPORT_STARTED_AT - timedelta(days=14)
    assert mr_window.end == _REPORT_STARTED_AT


def test_findings_carry_scope_name(api_client: TestClient, monkeypatch) -> None:
    """Each finding produced by a board signal includes scope_name matching the scope it was evaluated against."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, _BOARD_CAPABILITIES)

    signal_id = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "In Progress",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "status_category", "operator": "is", "value": "in_progress"}
                ],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "origin": "user_created",
        },
    ).json()["id"]
    group_id = api_client.post(
        "/api/signal-config-groups",
        json={"name": "Test group", "signal_ids": [signal_id]},
    ).json()["id"]

    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Scope name test team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "signal_config_group_ids": [group_id],
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    report = _run_report(api_client, team_id)
    findings = report["findings"]
    assert len(findings) > 0, "expected at least one finding from the in-progress work item"
    for finding in findings:
        assert finding["scope_name"] == "Platform Scrum"


def test_mr_findings_carry_scope_name(api_client: TestClient, monkeypatch) -> None:
    """MR findings produced by a merge_request signal include scope_name == 'code'."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector, _LinkingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    jira_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, jira_id, _BOARD_CAPABILITIES)
    gitlab_id = _create_gitlab_connection(api_client)

    signal_id = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Open MR",
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
    group_id = api_client.post(
        "/api/signal-config-groups",
        json={"name": "MR group", "signal_ids": [signal_id]},
    ).json()["id"]

    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "MR scope name team",
            "connection_ids": [jira_id],
            "scope_ids": [scope_id],
            "code_connection_id": gitlab_id,
            "signal_config_group_ids": [group_id],
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    report = _run_report(api_client, team_id)
    mr_findings = [f for f in report["findings"] if f["entity_type"] == "mergerequest"]
    assert len(mr_findings) > 0, "expected at least one MR finding from the open MR"
    for finding in mr_findings:
        assert finding["scope_name"] == "code"
