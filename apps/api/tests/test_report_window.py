"""Tests for M6-02: the report runner derives the default EvaluationWindow from the team's
working mode and persists it against the run's team and start time.

These assert the PERSISTED window row (loaded from the report's evaluation_window_id), which
the MR-fetch-window tests in test_report_runner.py do not cover. The no-source 422 case lives
in test_report_source_guard.py (test_no_source_returns_422) and is not duplicated here.

Scenarios:
  - Scrum team with a board + active sprint → SPRINT window referencing the persisted sprint.
  - Kanban team with a board → DATE_RANGE window (now-14 days .. now).
  - Code-only kanban team (no board) → DATE_RANGE window, proving working-mode derivation
    without a board.
  - Code-only scrum team (no board) → DATE_RANGE fallback via the `sprints is None` disjunct.
  - Scrum team with a board but no active sprint → HTTP 422 (no silent date-range fallback).
"""

from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_core.models import Source, Sprint, SprintState, WindowType

from em_radar_api.tables import EvaluationWindowTable, ReportTable, SprintTable
from test_report_runner import _RecordingMRConnector, _create_gitlab_connection
from test_source_connection_routes import (
    FrozenReportDateTime,
    JiraTestConnector,
    _REPORT_STARTED_AT,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
)

_BOARD_CAPABILITIES = ["sprint", "statuses", "labels"]


class _JiraNoActiveSprintConnector(JiraTestConnector):
    """Jira fake whose board has only non-active (future/closed) sprints."""

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        assert board_id == "20000"
        return [
            Sprint(
                id="45cdfd02-9cde-4c65-a618-7728fc9fb495",
                source=Source.JIRA,
                external_id="30000",
                board_id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                name="Platform Sprint 13",
                state=SprintState.FUTURE,
            )
        ]


def _persisted_window(
    session_factory: sessionmaker[Session], report_id: str
) -> EvaluationWindowTable:
    with session_factory() as session:
        report = session.get(ReportTable, UUID(report_id))
        assert report is not None
        window = session.get(EvaluationWindowTable, report.evaluation_window_id)
        assert window is not None
        return window


def test_scrum_board_persists_active_sprint_window(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scrum team with a board + active sprint: persisted window is SPRINT and references the
    active sprint's persisted internal id and the team's id."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )
    assert response.status_code == 200

    window = _persisted_window(session_factory, response.json()["id"])
    with session_factory() as session:
        active_sprint = session.exec(
            select(SprintTable).where(
                SprintTable.source == Source.JIRA, SprintTable.external_id == "30000"
            )
        ).one()

    assert window.window_type == WindowType.SPRINT
    assert window.sprint_id == active_sprint.id
    assert str(window.team_profile_id) == team_id


def test_kanban_board_persists_date_range_window(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kanban team with a board: persisted window is a DATE_RANGE of (now-14 days .. now),
    carries no sprint reference, and points at the team."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "kanban")

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )
    assert response.status_code == 200

    window = _persisted_window(session_factory, response.json()["id"])
    assert window.window_type == WindowType.DATE_RANGE
    assert window.sprint_id is None
    assert window.start == (_REPORT_STARTED_AT - timedelta(days=14)).replace(tzinfo=None)
    assert window.end == _REPORT_STARTED_AT.replace(tzinfo=None)
    assert str(window.team_profile_id) == team_id


def test_code_only_kanban_persists_date_range_window(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code-only kanban team (no board): working-mode derivation still yields a DATE_RANGE
    window bound to the team, with end == started_at (proving EvaluationContext.now)."""
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

    window = _persisted_window(session_factory, response.json()["id"])
    assert window.window_type == WindowType.DATE_RANGE
    assert window.sprint_id is None
    assert window.start == (_REPORT_STARTED_AT - timedelta(days=14)).replace(tzinfo=None)
    assert window.end == _REPORT_STARTED_AT.replace(tzinfo=None)
    assert str(window.team_profile_id) == team_id


def test_code_only_scrum_persists_date_range_window(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code-only SCRUM team (no board): the `sprints is None` fallback yields a DATE_RANGE
    window bound to the team. Guards the `or sprints is None` disjunct in the window helper
    (dropping it would make the scrum path iterate None → TypeError → HTTP 500)."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_RecordingMRConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    gitlab_id = _create_gitlab_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={
            "name": "Code only scrum",
            "code_connection_id": gitlab_id,
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )
    assert response.status_code == 200

    window = _persisted_window(session_factory, response.json()["id"])
    assert window.window_type == WindowType.DATE_RANGE
    assert window.sprint_id is None
    assert window.end == _REPORT_STARTED_AT.replace(tzinfo=None)
    assert str(window.team_profile_id) == team_id


def test_scrum_board_no_active_sprint_returns_422(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scrum team WITH a board but no active sprint is rejected with 422 and must NOT silently
    fall back to a date range (distinct from the no-source 422 in test_report_source_guard.py)."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_JiraNoActiveSprintConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 422
    assert "no active sprint" in response.json()["detail"]
