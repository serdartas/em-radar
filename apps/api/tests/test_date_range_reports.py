"""Tests for M6-03: the report runner accepts an explicit custom date-range window
(window_type=date_range + start/end) and uses it instead of the working-mode default, for
both scrum (ad-hoc) and kanban (default) teams.

Scenarios:
  - An explicit date-range run persists a DATE_RANGE window with the requested start/end,
    no sprint reference, bound to the team.
  - Sprint-only signals are window-gated on a date-range run (skipped with a note).
  - A scrum team runs an ad-hoc date-range report even when its board has no active sprint
    (the explicit window bypasses sprint derivation; no 422).
  - A date-range run whose Agile sprint endpoint is available preserves cached work-item→sprint
    linkage (no clobbering); a degraded run (endpoint unavailable) still succeeds AND keeps
    existing links / writes no unresolved connector ids; a healthy no-sprints fetch still
    reconciles (nulls dangling links) as before.
  - The scrum no-active-sprint 422 path closes the board connector (no HTTP-client leak).
  - Request validation: missing end / start >= end / explicit sprint / stray start-end → 422.
"""

from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_core.connectors import ConnectorTransientError
from em_radar_core.models import Source, Sprint, WindowType

from em_radar_api.tables import EvaluationWindowTable, ReportTable, SprintTable, WorkItemTable
from test_report_window import _JiraNoActiveSprintConnector
from test_source_connection_routes import (
    FrozenReportDateTime,
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
    _run_report,
)


class _SprintEndpointUnavailableConnector(JiraTestConnector):
    """Jira fake whose Agile sprint endpoint is unavailable; a date-range run must degrade."""

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        del board_id
        raise ConnectorTransientError("Agile sprint endpoint unavailable")


class _SprintlessLinkedItemConnector(JiraTestConnector):
    """Healthy board that genuinely returns no sprints; its work item still carries sprint refs
    (so a normal fetch must reconcile the dangling current_sprint_id to null, as before)."""

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        del board_id
        return []


class _ClosableNoActiveSprintConnector(_JiraNoActiveSprintConnector):
    """No-active-sprint fake that records close() calls, to prove the 422 path releases it."""

    close_calls: ClassVar[int] = 0

    async def close(self) -> None:
        type(self).close_calls += 1


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

    report = _run_report(
        api_client, team_id, window_type="date_range", start=_RANGE_START, end=_RANGE_END
    )

    window = _persisted_window(session_factory, report["id"])
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

    report = _run_report(
        api_client, team_id, window_type="date_range", start=_RANGE_START, end=_RANGE_END
    )

    skipped = report["signal_pack_snapshot"]["skipped_signals"]
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

    report = _run_report(
        api_client, team_id, window_type="date_range", start=_RANGE_START, end=_RANGE_END
    )

    window = _persisted_window(session_factory, report["id"])
    assert window.window_type == WindowType.DATE_RANGE
    assert window.sprint_id is None
    assert window.start == _RANGE_START_NAIVE
    assert window.end == _RANGE_END_NAIVE


def test_date_range_run_preserves_sprint_linkage(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the Agile endpoint is available, a date-range run re-resolves work-item→sprint links
    against current sprint identities instead of clobbering linkage cached by a prior run."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    # First a default (sprint) run persists PLAT-1 with a resolved current_sprint_id.
    _run_report(api_client, team_id)
    with session_factory() as session:
        sprint = session.exec(
            select(SprintTable).where(
                SprintTable.source == Source.JIRA, SprintTable.external_id == "30000"
            )
        ).one()
        workitem = session.exec(
            select(WorkItemTable).where(WorkItemTable.external_id == "PLAT-1")
        ).one()
        assert workitem.current_sprint_id == sprint.id
        assert sprint.id in workitem.sprint_ids

    # A date-range run must keep that linkage (sprints fetched best-effort and re-resolved).
    _run_report(api_client, team_id, window_type="date_range", start=_RANGE_START, end=_RANGE_END)

    with session_factory() as session:
        sprint = session.exec(
            select(SprintTable).where(
                SprintTable.source == Source.JIRA, SprintTable.external_id == "30000"
            )
        ).one()
        workitem = session.exec(
            select(WorkItemTable).where(WorkItemTable.external_id == "PLAT-1")
        ).one()
        assert workitem.current_sprint_id == sprint.id
        assert sprint.id in workitem.sprint_ids


def test_date_range_run_degrades_when_sprints_unavailable(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A date-range run must not depend on Agile sprint access: when list_sprints() fails, the
    run degrades to empty sprints (partial note), still succeeds, and persists work items."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_SprintEndpointUnavailableConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    report = _run_report(
        api_client, team_id, window_type="date_range", start=_RANGE_START, end=_RANGE_END
    )
    assert report["status"] == "succeeded"

    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    assert any(note["source"] == "sprints" for note in notes)

    # No prior linkage exists here, so the new work item must be written without unresolved
    # connector sprint ids (null current_sprint_id, empty sprint_ids) rather than corrupted.
    with session_factory() as session:
        workitem = session.exec(
            select(WorkItemTable).where(WorkItemTable.external_id == "PLAT-1")
        ).one_or_none()
    assert workitem is not None
    assert workitem.current_sprint_id is None
    assert workitem.sprint_ids == []


def test_date_range_degraded_run_preserves_existing_sprint_links(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A degraded date-range run (list_sprints fails) must NOT clobber sprint links cached by a
    prior healthy run: PLAT-1's current_sprint_id and sprint_ids stay unchanged."""
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    # A first healthy (default sprint) run caches the resolved work-item→sprint linkage.
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    _run_report(api_client, team_id)
    with session_factory() as session:
        sprint = session.exec(
            select(SprintTable).where(
                SprintTable.source == Source.JIRA, SprintTable.external_id == "30000"
            )
        ).one()
        workitem = session.exec(
            select(WorkItemTable).where(WorkItemTable.external_id == "PLAT-1")
        ).one()
        assert workitem.current_sprint_id == sprint.id
        assert workitem.sprint_ids == [sprint.id]
    cached_sprint_id = sprint.id

    # A degraded date-range run (sprint endpoint down) must leave that linkage untouched.
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_SprintEndpointUnavailableConnector],
    )
    _run_report(api_client, team_id, window_type="date_range", start=_RANGE_START, end=_RANGE_END)

    with session_factory() as session:
        workitem = session.exec(
            select(WorkItemTable).where(WorkItemTable.external_id == "PLAT-1")
        ).one()
        assert workitem.current_sprint_id == cached_sprint_id
        assert workitem.sprint_ids == [cached_sprint_id]


def test_healthy_run_without_sprints_reconciles_sprint_links(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A healthy fetch that genuinely returns no sprints must still reconcile normally: a work
    item's dangling current_sprint_id is nulled, as before (preservation only applies when the
    sprint endpoint is unavailable, not when there are legitimately no sprints)."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_SprintlessLinkedItemConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "kanban")

    report = _run_report(api_client, team_id)
    assert report["status"] == "succeeded"

    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    assert all(note["source"] != "sprints" for note in notes)

    with session_factory() as session:
        workitem = session.exec(
            select(WorkItemTable).where(WorkItemTable.external_id == "PLAT-1")
        ).one()
    assert workitem.current_sprint_id is None


def test_no_active_sprint_default_run_closes_connector(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A default scrum run whose board has no active sprint 422s AFTER the board connector is
    opened; that connector must be closed on the error path (no HTTP-client leak)."""
    _ClosableNoActiveSprintConnector.close_calls = 0
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_ClosableNoActiveSprintConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    job_resp = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )
    assert job_resp.status_code == 202
    job = api_client.get(f"/api/reports/jobs/{job_resp.json()['id']}").json()

    assert job["status"] == "failed"
    assert "no active sprint" in job["error"]
    assert _ClosableNoActiveSprintConnector.close_calls == 1


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

    report = _run_report(
        api_client,
        team_id,
        window_type="date_range",
        start=_RANGE_START_NO_TZ,
        end=_RANGE_END_NO_TZ,
    )

    window = _persisted_window(session_factory, report["id"])
    assert window.window_type == WindowType.DATE_RANGE
    assert window.start == _RANGE_START_NAIVE
    assert window.end == _RANGE_END_NAIVE


@pytest.mark.parametrize(
    "window_payload",
    [
        {"window_type": "date_range", "start": _RANGE_START},
        {"window_type": "date_range", "start": _RANGE_END, "end": _RANGE_START},
        {"window_type": "date_range", "start": _RANGE_START, "end": _RANGE_START},
        {"window_type": "date_range", "start": _RANGE_START, "end": _RANGE_END, "sprint_external_id": "30000"},
        {"start": _RANGE_START, "end": _RANGE_END},
    ],
    ids=[
        "missing-end",
        "start-after-end",
        "start-equals-end",
        "sprint-external-id-on-date-range-rejected",
        "stray-start-end-without-window-type",
    ],
)
def test_invalid_window_request_returns_422(
    api_client: TestClient,
    window_payload: dict[str, str],
) -> None:
    """Malformed window requests are rejected with 422 at request validation, before any team
    lookup: bad date_range bounds, sprint_external_id on non-sprint window, and stray start/end."""
    response = api_client.post(
        "/api/reports/run",
        json={"connector": "jira", "team_profile_id": str(uuid4()), **window_payload},
    )
    assert response.status_code == 422
