from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.db import _write_lock
from em_radar_api.tables import EvaluationWindowTable, ReportTable
from em_radar_core.models import Source, Sprint, SprintState, WindowType
from test_source_connection_routes import (
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
    _run_report,
)

_BOARD_CAPABILITIES = ["sprint", "statuses", "labels"]


def _use_jira_connector(monkeypatch) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )


def _create_signal(api_client: TestClient, name: str) -> str:
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
            "origin": "user_created",
        },
    ).json()["id"]


def _create_group(api_client: TestClient, name: str, signal_ids: list[str]) -> str:
    return api_client.post(
        "/api/signal-config-groups",
        json={"name": name, "signal_ids": signal_ids},
    ).json()["id"]


def test_run_evaluates_union_of_enabled_group_signals(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    signal_a = _create_signal(api_client, "Signal A")
    signal_b = _create_signal(api_client, "Signal B")
    ungrouped = _create_signal(api_client, "Ungrouped signal")
    group_a = _create_group(api_client, "Group A", [signal_a])
    group_b = _create_group(api_client, "Group B", [signal_b])
    team_id = _create_jira_team(
        api_client,
        connection_id,
        scope_id,
        "scrum",
        sprint_length_days=14,
        group_ids=[group_a, group_b],
    )

    report = _run_report(api_client, team_id)

    signal_ids = {finding["signal_id"] for finding in report["findings"]}
    assert signal_ids == {signal_a, signal_b}
    assert ungrouped not in signal_ids


def test_signal_in_no_attached_group_does_not_run(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    grouped = _create_signal(api_client, "Grouped")
    ungrouped = _create_signal(api_client, "Ungrouped")
    group = _create_group(api_client, "Group", [grouped])
    team_id = _create_jira_team(
        api_client, connection_id, scope_id, "scrum", sprint_length_days=14, group_ids=[group]
    )

    report = _run_report(api_client, team_id)

    signal_ids = {finding["signal_id"] for finding in report["findings"]}
    assert grouped in signal_ids
    assert ungrouped not in signal_ids


def test_all_group_attached_signals_are_evaluated(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    signal_a = _create_signal(api_client, "Signal X")
    signal_b = _create_signal(api_client, "Signal Y")
    group = _create_group(api_client, "Group XY", [signal_a, signal_b])
    team_id = _create_jira_team(
        api_client, connection_id, scope_id, "scrum", sprint_length_days=14, group_ids=[group]
    )

    report = _run_report(api_client, team_id)

    signal_ids = {finding["signal_id"] for finding in report["findings"]}
    assert signal_a in signal_ids
    assert signal_b in signal_ids


def test_two_teams_sharing_a_group_both_evaluate_it(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    signal_id = _create_signal(api_client, "Shared signal")
    group = _create_group(api_client, "Shared group", [signal_id])
    team_one = _create_jira_team(
        api_client, connection_id, scope_id, "scrum", sprint_length_days=14, group_ids=[group]
    )
    team_two = _create_jira_team(
        api_client, connection_id, scope_id, "scrum", sprint_length_days=14, group_ids=[group]
    )

    first = _run_report(api_client, team_one)
    second = _run_report(api_client, team_two)

    assert signal_id in {finding["signal_id"] for finding in first["findings"]}
    assert signal_id in {finding["signal_id"] for finding in second["findings"]}


def test_snapshot_records_group_ids_and_signal_set(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    signal_id = _create_signal(api_client, "Snapshot signal")
    group = _create_group(api_client, "Snapshot group", [signal_id])
    team_id = _create_jira_team(
        api_client, connection_id, scope_id, "scrum", sprint_length_days=14, group_ids=[group]
    )

    report = _run_report(api_client, team_id)

    snapshot = report["signal_pack_snapshot"]
    assert snapshot["signal_config_group_ids"] == [group]
    assert [definition["id"] for definition in snapshot["signal_definitions"]] == [signal_id]

    # Extended fields added in M8.5-04: expression, severity, message_template.
    signal_entry = snapshot["signal_definitions"][0]
    assert "expression" in signal_entry
    assert signal_entry["expression"] == {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "status_category", "operator": "is", "value": "in_progress"}],
    }
    assert signal_entry["severity"] == "warning"
    assert signal_entry["message_template"] is None


def test_report_history_exposes_team_identity(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    signal_id = _create_signal(api_client, "Team identity signal")
    group = _create_group(api_client, "Team identity group", [signal_id])
    team_id = _create_jira_team(
        api_client, connection_id, scope_id, "scrum", sprint_length_days=14, group_ids=[group]
    )
    team_name = api_client.get(f"/api/teams/{team_id}").json()["name"]

    report = _run_report(api_client, team_id)
    report_id = report["id"]

    listing = api_client.get("/api/reports")
    assert listing.status_code == 200
    summaries = {r["id"]: r for r in listing.json()}
    assert summaries[report_id]["team_profile_id"] == team_id
    assert summaries[report_id]["team_name"] == team_name

    detail = api_client.get(f"/api/reports/{report_id}")
    assert detail.status_code == 200
    assert detail.json()["team_profile_id"] == team_id
    assert detail.json()["team_name"] == team_name


def test_run_requires_team_with_at_least_one_source(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    # Team with a Jira connection but no board scope and no code_connection_id has no sources.
    team_id = api_client.post(
        "/api/teams",
        json={"name": "No scope", "connection_ids": [connection_id]},
    ).json()["id"]

    job_resp = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert job_resp.status_code == 202
    job_id = job_resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert "no source" in job["error"]


# ---------------------------------------------------------------------------
# Job endpoint tests (M8.3-02)
# ---------------------------------------------------------------------------


def test_run_returns_job_id_and_202(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    resp = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert resp.status_code == 202
    job = resp.json()
    assert "id" in job
    assert job["team_profile_id"] == team_id
    assert job["status"] in ("queued", "running", "done", "failed")
    assert "enqueued_at" in job


def test_job_polling_returns_terminal_status(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    job_resp = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )
    assert job_resp.status_code == 202
    job_id = job_resp.json()["id"]

    # BackgroundTasks completes during the POST; GET reflects the terminal state
    polled = api_client.get(f"/api/reports/jobs/{job_id}")
    assert polled.status_code == 200
    job = polled.json()
    assert job["status"] in ("done", "failed")
    assert job["started_at"] is not None
    assert job["finished_at"] is not None


def test_job_list_returns_recent_runs(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    api_client.post("/api/reports/run", json={"connector": "jira", "team_profile_id": team_id})
    api_client.post("/api/reports/run", json={"connector": "jira", "team_profile_id": team_id})

    jobs_resp = api_client.get("/api/reports/jobs")
    assert jobs_resp.status_code == 200
    jobs = jobs_resp.json()
    assert len(jobs) == 2
    for job in jobs:
        assert "id" in job
        assert "status" in job
        assert "enqueued_at" in job
        assert "started_at" in job
        assert "finished_at" in job


def test_failed_run_records_failed_status_and_error(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    # No scope → job fails with "no source" error
    team_id = api_client.post(
        "/api/teams",
        json={"name": "No source for failure test", "connection_ids": [connection_id]},
    ).json()["id"]

    job_resp = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )
    assert job_resp.status_code == 202
    job_id = job_resp.json()["id"]

    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error"] is not None
    assert "no source" in job["error"]
    assert job["report_id"] is None
    assert job["finished_at"] is not None


def test_unknown_job_id_returns_404(api_client: TestClient) -> None:
    resp = api_client.get("/api/reports/jobs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_done_job_links_to_report(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    job_resp = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )
    assert job_resp.status_code == 202
    job_id = job_resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "done"
    assert job["report_id"] is not None

    report = api_client.get(f"/api/reports/{job['report_id']}")
    assert report.status_code == 200
    assert report.json()["status"] == "succeeded"


def test_write_lock_not_held_during_connector_io(api_client: TestClient, monkeypatch) -> None:
    """AUDIT-7 / M8.3-03: _write_lock must be released before connector I/O begins.

    The background job uses write_session() only for the DB write phases (mark running,
    persist result). Connector fetch calls run outside that context manager, so other write
    endpoints are not serialized behind a long-running report fetch.
    """
    lock_state_during_io: list[bool] = []
    lock_acquirable_during_io: list[bool] = []

    from em_radar_core.models import EvaluationWindow

    class _LockCheckingConnector(JiraTestConnector):
        """Records write-lock state when fetch_workitems is called."""

        async def fetch_workitems(  # type: ignore[override]
            self, scope: object, window: EvaluationWindow
        ) -> AsyncIterator[object]:
            lock_state_during_io.append(_write_lock.locked())
            # A non-blocking acquire succeeds iff the lock is free, proving a concurrent
            # writer (e.g. create-connection, edit-signal) would not be serialized here.
            acquired = _write_lock.acquire(blocking=False)
            lock_acquirable_during_io.append(acquired)
            if acquired:
                _write_lock.release()
            async for item in super().fetch_workitems(scope, window):  # type: ignore[misc]
                yield item

    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_LockCheckingConnector],
    )

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    _run_report(api_client, team_id)

    assert lock_state_during_io, "fetch_workitems was never called"
    assert not any(lock_state_during_io), (
        "_write_lock was held during connector I/O; lock must be released before fetch"
    )
    assert all(lock_acquirable_during_io), (
        "concurrent writer could not acquire _write_lock during connector I/O"
    )


def test_run_report_does_not_hold_write_lock_across_background_task(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: /reports/run must release _write_lock before its background task runs.

    If run_report keeps the lock (e.g. via get_write_session, whose yield-dependency exit
    stack is closed only *after* Starlette executes background tasks), the async job's
    write_session() re-acquires the same lock on the event-loop thread and deadlocks the
    server. This test exercises the real DB dependencies (real _write_lock) against a temp
    engine, since the conftest fixture overrides them with a lock-free session and would hide
    the deadlock. The probe uses a timeout so a reintroduced bug fails fast instead of hanging.
    """
    from datetime import UTC, datetime

    from sqlmodel import SQLModel

    import em_radar_api.db as db_module
    import em_radar_api.routers.reports as reports_module
    from em_radar_api.db import (
        create_db_engine,
        create_session_factory,
        get_session,
        get_session_factory,
        get_write_session,
    )
    from em_radar_api.main import app
    from em_radar_api.tables import TeamProfileTable

    engine = create_db_engine(tmp_path / "lock-regression.db")
    SQLModel.metadata.create_all(engine)
    sf = create_session_factory(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "session_factory", sf)

    with sf() as session:
        now = datetime.now(UTC)
        team = TeamProfileTable(name="Lock Regression Team", created_at=now, updated_at=now)
        session.add(team)
        session.commit()
        team_id = str(team.id)

    lock_free_in_task: list[bool] = []

    def _probe(job_id: object, *args: object, **kwargs: object) -> None:
        acquired = _write_lock.acquire(timeout=1.0)
        lock_free_in_task.append(acquired)
        if acquired:
            _write_lock.release()

    monkeypatch.setattr(reports_module, "_run_report_job", _probe)

    # Use the real dependencies (no lock-free overrides) so run_report takes the real lock.
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_write_session, None)
    app.dependency_overrides.pop(get_session_factory, None)
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert resp.status_code == 202
    assert lock_free_in_task == [True], (
        "run_report held _write_lock while the background task ran; the async job would "
        "deadlock re-acquiring it on the event-loop thread"
    )


# ---------------------------------------------------------------------------
# Sprint window tests (M8.3-04)
# ---------------------------------------------------------------------------


def _get_window(sf: sessionmaker[Session], report_id: str) -> EvaluationWindowTable:
    with sf() as session:
        report = session.get(ReportTable, UUID(report_id))
        assert report is not None
        window = session.get(EvaluationWindowTable, report.evaluation_window_id)
        assert window is not None
        return window


def test_sprint_window_type_accepted_and_uses_active_sprint(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """window_type=sprint without sprint_external_id uses the board's active sprint."""
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    resp = api_client.post(
        "/api/reports/run",
        json={"connector": "jira", "team_profile_id": team_id, "window_type": "sprint"},
    )

    assert resp.status_code == 202
    job_id = resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "done", f"job failed: {job.get('error')}"
    window = _get_window(session_factory, job["report_id"])
    assert window.window_type is WindowType.SPRINT


def test_sprint_window_with_explicit_sprint_external_id(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """window_type=sprint with start==end sprint range resolves to the specified sprint."""
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    # The JiraTestConnector has a sprint with external_id="30000"; start==end is single-sprint.
    resp = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "sprint",
            "start_sprint_external_id": "30000",
            "end_sprint_external_id": "30000",
        },
    )

    assert resp.status_code == 202
    job_id = resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "done", f"job failed: {job.get('error')}"
    window = _get_window(session_factory, job["report_id"])
    assert window.window_type is WindowType.SPRINT


def test_sprint_external_id_not_found_returns_failed_job(
    api_client: TestClient, monkeypatch
) -> None:
    """A sprint range whose start is not on the board results in a failed job."""
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    resp = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "sprint",
            "start_sprint_external_id": "99999",
            "end_sprint_external_id": "99999",
        },
    )

    assert resp.status_code == 202
    job_id = resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert "99999" in job["error"]


def test_team_sprints_endpoint_returns_board_sprints(api_client: TestClient, monkeypatch) -> None:
    """GET /api/teams/{id}/sprints returns the board's sprints."""
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    resp = api_client.get(f"/api/teams/{team_id}/sprints")

    assert resp.status_code == 200
    sprints = resp.json()
    assert len(sprints) >= 1
    assert sprints[0]["external_id"] == "30000"
    assert sprints[0]["name"] == "Platform Sprint 12"
    assert sprints[0]["state"] == "active"


def test_team_sprints_no_board_scope_returns_empty(api_client: TestClient, monkeypatch) -> None:
    """GET /api/teams/{id}/sprints returns [] for a team without a board scope."""
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    team_id = api_client.post(
        "/api/teams",
        json={"name": "No scope team", "connection_ids": [connection_id]},
    ).json()["id"]

    resp = api_client.get(f"/api/teams/{team_id}/sprints")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Sprint range tests (M8.7-10)
# ---------------------------------------------------------------------------

_RANGE_SPRINT_1_START = datetime(2026, 5, 1, tzinfo=UTC)
_RANGE_SPRINT_1_END = datetime(2026, 5, 14, tzinfo=UTC)
_RANGE_SPRINT_2_START = datetime(2026, 5, 15, tzinfo=UTC)
_RANGE_SPRINT_2_END = datetime(2026, 5, 28, tzinfo=UTC)
_RANGE_SPRINT_2_COMPLETE = datetime(2026, 5, 28, tzinfo=UTC)


class _JiraTwoSprintConnector(JiraTestConnector):
    """Jira fake exposing two closed sprints with concrete start/end dates."""

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        assert board_id == "20000"
        return [
            Sprint(
                id="aaaaaaaa-0001-0001-0001-aaaaaaaaaaaa",
                source=Source.JIRA,
                external_id="sp-1",
                board_id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                name="Sprint 1",
                state=SprintState.CLOSED,
                start_date=_RANGE_SPRINT_1_START,
                end_date=_RANGE_SPRINT_1_END,
                complete_date=_RANGE_SPRINT_1_END,
            ),
            Sprint(
                id="bbbbbbbb-0002-0002-0002-bbbbbbbbbbbb",
                source=Source.JIRA,
                external_id="sp-2",
                board_id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                name="Sprint 2",
                state=SprintState.CLOSED,
                start_date=_RANGE_SPRINT_2_START,
                end_date=_RANGE_SPRINT_2_END,
                complete_date=_RANGE_SPRINT_2_COMPLETE,
            ),
        ]


class _JiraTwoSprintNoDateConnector(JiraTestConnector):
    """Jira fake with two sprints where the first has no start_date."""

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        assert board_id == "20000"
        return [
            Sprint(
                id="cccccccc-0003-0003-0003-cccccccccccc",
                source=Source.JIRA,
                external_id="sp-a",
                board_id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                name="Sprint A (no dates)",
                state=SprintState.CLOSED,
            ),
            Sprint(
                id="dddddddd-0004-0004-0004-dddddddddddd",
                source=Source.JIRA,
                external_id="sp-b",
                board_id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                name="Sprint B",
                state=SprintState.CLOSED,
                start_date=datetime(2026, 6, 1, tzinfo=UTC),
                end_date=datetime(2026, 6, 14, tzinfo=UTC),
                complete_date=datetime(2026, 6, 14, tzinfo=UTC),
            ),
        ]


def _use_two_sprint_connector(monkeypatch) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_JiraTwoSprintConnector],
    )


def test_sprint_range_resolves_to_date_range_window(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start_sprint_external_id != end_sprint_external_id resolves to a DATE_RANGE window."""
    _use_two_sprint_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    resp = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "sprint",
            "start_sprint_external_id": "sp-1",
            "end_sprint_external_id": "sp-2",
        },
    )

    assert resp.status_code == 202
    job_id = resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "done", f"job failed: {job.get('error')}"
    window = _get_window(session_factory, job["report_id"])
    assert window.window_type is WindowType.DATE_RANGE
    # SQLite stores datetimes without timezone; compare against naive UTC equivalents.
    assert window.start == _RANGE_SPRINT_1_START.replace(tzinfo=None)
    assert window.end == _RANGE_SPRINT_2_COMPLETE.replace(tzinfo=None)


def test_sprint_range_single_sprint_produces_sprint_window(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start == end sprint range preserves sprint-window semantics (work items by membership)."""
    _use_two_sprint_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    resp = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "sprint",
            "start_sprint_external_id": "sp-1",
            "end_sprint_external_id": "sp-1",
        },
    )

    assert resp.status_code == 202
    job_id = resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "done", f"job failed: {job.get('error')}"
    window = _get_window(session_factory, job["report_id"])
    assert window.window_type is WindowType.SPRINT


def test_sprint_range_start_after_end_returns_failed_job(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A range where start sprint begins after end sprint fails with a descriptive error."""
    _use_two_sprint_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    resp = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "sprint",
            "start_sprint_external_id": "sp-2",
            "end_sprint_external_id": "sp-1",
        },
    )

    assert resp.status_code == 202
    job_id = resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert "sp-2" in job["error"]
    assert "sp-1" in job["error"]


def test_sprint_range_end_not_on_board_returns_failed_job(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A range where the end sprint is not on the board fails with a descriptive error."""
    _use_two_sprint_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    resp = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": team_id,
            "window_type": "sprint",
            "start_sprint_external_id": "sp-1",
            "end_sprint_external_id": "sp-999",
        },
    )

    assert resp.status_code == 202
    job_id = resp.json()["id"]
    job = api_client.get(f"/api/reports/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert "sp-999" in job["error"]


def test_sprint_range_requires_both_fields_to_be_provided(api_client: TestClient) -> None:
    """Providing only one of the sprint range fields is rejected with 422."""
    from uuid import uuid4

    resp = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": str(uuid4()),
            "window_type": "sprint",
            "start_sprint_external_id": "sp-1",
        },
    )
    assert resp.status_code == 422


def test_sprint_range_fields_rejected_on_non_sprint_window(api_client: TestClient) -> None:
    """Sprint range fields on a date_range window are rejected with 422."""
    from uuid import uuid4

    resp = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "team_profile_id": str(uuid4()),
            "window_type": "date_range",
            "start": "2026-05-01T00:00:00Z",
            "end": "2026-05-15T00:00:00Z",
            "start_sprint_external_id": "sp-1",
            "end_sprint_external_id": "sp-2",
        },
    )
    assert resp.status_code == 422
