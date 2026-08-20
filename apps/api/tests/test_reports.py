from fastapi.testclient import TestClient

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
