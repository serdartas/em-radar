"""Tests for M6-03: the report runner accepts an explicit custom date-range window
(window_type=date_range + start/end) and uses it instead of the working-mode default, for
both scrum (ad-hoc) and kanban (default) teams.

Scenarios:
  - An explicit date-range run persists a DATE_RANGE window with the requested start/end,
    no sprint reference, bound to the team.
  - Sprint-only signals are window-gated on a date-range run (skipped with a note).
  - A scrum team runs an ad-hoc date-range report even when its board has no active sprint
    (the explicit window bypasses sprint derivation; no 422).
  - Request validation: missing end / start >= end return 422.
"""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_core.models import WindowType

from em_radar_api.tables import EvaluationWindowTable, ReportTable
from test_report_window import _JiraNoActiveSprintConnector
from test_source_connection_routes import (
    FrozenReportDateTime,
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
)

_BOARD_CAPABILITIES = ["sprint", "statuses", "labels"]
_RANGE_START = "2026-05-01T00:00:00Z"
_RANGE_END = "2026-06-01T00:00:00Z"
_RANGE_START_NAIVE = datetime(2026, 5, 1, 0, 0, 0)
_RANGE_END_NAIVE = datetime(2026, 6, 1, 0, 0, 0)
_RANGE_START_NO_TZ = "2026-05-01T00:00:00"
_RANGE_END_NO_TZ = "2026-06-01T00:00:00"


def _persisted_window(
    session_factory: sessionmaker[Session], report_id: str
) -> EvaluationWindowTable:
    with session_factory() as session:
        report = session.get(ReportTable, UUID(report_id))
        assert report is not None
        window = session.get(EvaluationWindowTable, report.evaluation_window_id)
        assert window is not None
        return window


def _create_sprint_field_group(api_client: TestClient) -> str:
    """A signal-config group holding one board signal that uses a sprint-only field."""
    definition = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Late sprint scope churn",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [{"field": "sprint_day", "operator": "is_after", "value": 1}],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "enabled": True,
            "origin": "user_created",
        },
    ).json()
    return api_client.post(
        "/api/signal-config-groups",
        json={"name": "Sprint signals", "signal_ids": [definition["id"]]},
    ).json()["id"]


def test_date_range_run_persists_requested_window(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit date_range run persists a DATE_RANGE window with the requested start/end,
    no sprint reference, and the team's id."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    response = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "date_range",
            "start": _RANGE_START,
            "end": _RANGE_END,
        },
    )
    assert response.status_code == 200

    window = _persisted_window(session_factory, response.json()["id"])
    assert window.window_type == WindowType.DATE_RANGE
    assert window.sprint_id is None
    assert window.start == _RANGE_START_NAIVE
    assert window.end == _RANGE_END_NAIVE
    assert str(window.team_profile_id) == team_id


def test_date_range_run_skips_sprint_only_signals(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sprint-field signal is window-gated on a date-range run and recorded as skipped with
    the 'requires a sprint window' note."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    group_id = _create_sprint_field_group(api_client)
    team_id = _create_jira_team(
        api_client,
        connection_id,
        scope_id,
        "scrum",
        sprint_length_days=14,
        group_ids=[group_id],
    )

    response = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "date_range",
            "start": _RANGE_START,
            "end": _RANGE_END,
        },
    )
    assert response.status_code == 200

    skipped = response.json()["signal_pack_snapshot"]["skipped_signals"]
    assert any(
        entry["name"] == "Late sprint scope churn" and entry["reason"] == "requires a sprint window"
        for entry in skipped
    )


def test_scrum_ad_hoc_date_range_bypasses_no_active_sprint(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scrum team whose board has no active sprint can still run an ad-hoc date-range report:
    the explicit window bypasses sprint derivation, so no 422 is raised."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_JiraNoActiveSprintConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    response = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "date_range",
            "start": _RANGE_START,
            "end": _RANGE_END,
        },
    )
    assert response.status_code == 200

    window = _persisted_window(session_factory, response.json()["id"])
    assert window.window_type == WindowType.DATE_RANGE
    assert window.sprint_id is None
    assert window.start == _RANGE_START_NAIVE
    assert window.end == _RANGE_END_NAIVE


def test_naive_date_range_treated_as_utc(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Naive start/end (ISO without Z/offset) are assumed UTC, so the persisted window's
    start/end equal the same instants as the tz-aware case."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    response = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "date_range",
            "start": _RANGE_START_NO_TZ,
            "end": _RANGE_END_NO_TZ,
        },
    )
    assert response.status_code == 200

    window = _persisted_window(session_factory, response.json()["id"])
    assert window.window_type == WindowType.DATE_RANGE
    assert window.start == _RANGE_START_NAIVE
    assert window.end == _RANGE_END_NAIVE


@pytest.mark.parametrize(
    "window_payload",
    [
        {"window_type": "date_range", "start": _RANGE_START},
        {"window_type": "date_range", "start": _RANGE_END, "end": _RANGE_START},
        {"window_type": "date_range", "start": _RANGE_START, "end": _RANGE_START},
        {"window_type": "sprint"},
        {"start": _RANGE_START, "end": _RANGE_END},
    ],
    ids=[
        "missing-end",
        "start-after-end",
        "start-equals-end",
        "explicit-sprint-rejected",
        "stray-start-end-without-window-type",
    ],
)
def test_invalid_window_request_returns_422(
    api_client: TestClient,
    window_payload: dict[str, str],
) -> None:
    """Malformed window requests are rejected with 422 at request validation, before any team
    lookup: bad date_range bounds, explicit sprint selection, and stray start/end."""
    response = api_client.post(
        "/api/reports/run",
        json={"connector": "jira", "team_profile_id": str(uuid4()), **window_payload},
    )
    assert response.status_code == 422
