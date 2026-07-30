from fastapi.testclient import TestClient

from test_source_connection_routes import (
    JiraTestConnector,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
)

_BOARD_CAPABILITIES = ["sprint", "statuses", "labels"]


def _use_jira_connector(monkeypatch) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )


def _create_signal(api_client: TestClient, name: str, enabled: bool = True) -> str:
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
            "enabled": enabled,
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

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 200
    signal_ids = {finding["signal_id"] for finding in response.json()["findings"]}
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

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    signal_ids = {finding["signal_id"] for finding in response.json()["findings"]}
    assert grouped in signal_ids
    assert ungrouped not in signal_ids


def test_disabled_signal_in_group_is_not_evaluated(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    enabled = _create_signal(api_client, "Enabled")
    disabled = _create_signal(api_client, "Disabled", enabled=False)
    group = _create_group(api_client, "Group", [enabled, disabled])
    team_id = _create_jira_team(
        api_client, connection_id, scope_id, "scrum", sprint_length_days=14, group_ids=[group]
    )

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    signal_ids = {finding["signal_id"] for finding in response.json()["findings"]}
    assert enabled in signal_ids
    assert disabled not in signal_ids


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

    first = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_one}
    )
    second = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_two}
    )

    assert signal_id in {finding["signal_id"] for finding in first.json()["findings"]}
    assert signal_id in {finding["signal_id"] for finding in second.json()["findings"]}


def test_snapshot_records_group_ids_and_signal_set(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, _BOARD_CAPABILITIES)
    signal_id = _create_signal(api_client, "Snapshot signal")
    group = _create_group(api_client, "Snapshot group", [signal_id])
    team_id = _create_jira_team(
        api_client, connection_id, scope_id, "scrum", sprint_length_days=14, group_ids=[group]
    )

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    snapshot = response.json()["signal_pack_snapshot"]
    assert snapshot["signal_config_group_ids"] == [group]
    assert [definition["id"] for definition in snapshot["signal_definitions"]] == [signal_id]


def test_run_requires_team_with_at_least_one_source(api_client: TestClient, monkeypatch) -> None:
    _use_jira_connector(monkeypatch)
    connection_id = _create_jira_connection(api_client)
    # Team with a Jira connection but no board scope and no code_connection_id has no sources.
    team_id = api_client.post(
        "/api/teams",
        json={"name": "No scope", "connection_ids": [connection_id]},
    ).json()["id"]

    response = api_client.post(
        "/api/reports/run", json={"connector": "jira", "team_profile_id": team_id}
    )

    assert response.status_code == 422
    assert "no source" in response.json()["detail"]
