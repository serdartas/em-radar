from fastapi.testclient import TestClient


def _create_scoped_signal(api_client: TestClient) -> tuple[str, str]:
    connection = api_client.post(
        "/api/connections",
        json={
            "connector_name": "jira",
            "config": {"base_url": "https://example.atlassian.net", "token": "secret-token"},
        },
    ).json()
    scope = api_client.post(
        "/api/scopes",
        json={
            "connection_id": connection["id"],
            "name": "Fraud Defense Scrum Board",
            "scope_type": "board",
            "external_ref": {
                "type": "jira_board",
                "id": "123",
                "key": None,
                "name": "Fraud Defense Scrum Board",
            },
            "capabilities": ["sprint", "statuses", "labels"],
        },
    ).json()
    signal_response = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Stale fraud work",
            "description": "Finds stale work.",
            "entity_type": "issue",
            "target_scopes": [
                {
                    "connector_id": connection["id"],
                    "scope_id": scope["id"],
                    "scope_type": "board",
                }
            ],
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {
                        "field": "age_in_current_status",
                        "operator": "greater_than",
                        "value": {"amount": 3, "unit": "days"},
                    }
                ],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "enabled": True,
            "origin": "user_created",
            "template_key": None,
        },
    )
    assert signal_response.status_code == 201
    return connection["id"], scope["id"]


def test_private_export_preserves_scope_mappings_without_secrets(api_client: TestClient) -> None:
    connection_id, scope_id = _create_scoped_signal(api_client)

    response = api_client.get("/api/signal-pack/export?export_type=private_backup")
    text = response.text

    assert response.status_code == 200
    assert connection_id in text
    assert scope_id in text
    assert "Fraud Defense Scrum Board" in text
    assert "secret-token" not in text
    assert "****" not in text


def test_public_export_removes_org_specific_scope_data(api_client: TestClient) -> None:
    _create_scoped_signal(api_client)

    text = api_client.get("/api/signal-pack/export?export_type=public_template").text

    assert "public_template" in text
    assert "templates:" in text
    assert "123" not in text
    assert "Fraud Defense Scrum Board" not in text
    assert "example.atlassian.net" not in text


def test_public_template_import_keeps_unresolved_signals_disabled(api_client: TestClient) -> None:
    raw_yaml = """
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: public-stale-work
  version: 0.1.0
  description: Public stale work template.
spec:
  export_type: public_template
  templates:
    - key: public-stale-work
      name: Public stale work
      required_connector_type: jira
      entity_type: issue
      required_scope_capabilities: [statuses]
      expression:
        type: group
        operator: all
        conditions:
          - field: status_category
            operator: is
            value: in_progress
      report_settings:
        severity: warning
        category: flow
      enabled_by_default: true
"""

    preview = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": raw_yaml, "mode": "additive"},
    )
    assert preview.status_code == 200
    assert preview.json()["unresolved_mappings"] == ["public-stale-work"]

    apply = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": raw_yaml, "mode": "additive"},
    )
    assert apply.status_code == 200

    definitions = api_client.get("/api/signal-definitions").json()
    imported = next(
        definition for definition in definitions if definition["name"] == "Public stale work"
    )
    assert imported["enabled"] is False
    assert imported["target_scopes"] == []


def test_private_backup_import_remaps_matching_scope(api_client: TestClient) -> None:
    connection = api_client.post(
        "/api/connections",
        json={"connector_name": "jira", "config": {"base_url": "https://local.invalid"}},
    ).json()
    local_scope = api_client.post(
        "/api/scopes",
        json={
            "connection_id": connection["id"],
            "name": "Local Scrum Board",
            "scope_type": "board",
            "external_ref": {
                "type": "jira_board",
                "id": "20000",
                "key": None,
                "name": "Platform Scrum",
            },
            "capabilities": ["sprint", "statuses", "labels"],
        },
    ).json()
    raw_yaml = """
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: private-stale-work
  version: 0.1.0
  description: Private backup.
spec:
  export_type: private_backup
  scopes:
    - local_ref: old-scope-id
      connector_ref: old-connector-id
      name: Platform Scrum
      scope_type: board
      external_ref:
        type: jira_board
        id: "20000"
        key: null
        name: Platform Scrum
      capabilities: [sprint, statuses, labels]
  signals:
    - id: old-signal-id
      name: Imported scoped stale work
      entity_type: issue
      target_scopes:
        - connector_id: old-connector-id
          scope_id: old-scope-id
          scope_type: board
      expression:
        type: group
        operator: all
        conditions:
          - field: status_category
            operator: is
            value: in_progress
      report_settings:
        severity: warning
        category: flow
      enabled: true
      origin: imported
"""

    preview = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": raw_yaml, "mode": "additive"},
    )
    assert preview.status_code == 200
    assert preview.json().get("unresolved_mappings", []) == []

    apply = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": raw_yaml, "mode": "additive"},
    )
    assert apply.status_code == 200

    imported = next(
        definition
        for definition in api_client.get("/api/signal-definitions").json()
        if definition["name"] == "Imported scoped stale work"
    )
    assert imported["enabled"] is True
    assert imported["target_scopes"] == [
        {
            "connector_id": connection["id"],
            "scope_id": local_scope["id"],
            "scope_type": "board",
        }
    ]


def test_private_backup_import_disables_unresolved_scope(api_client: TestClient) -> None:
    raw_yaml = """
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: unresolved-private-stale-work
  version: 0.1.0
  description: Private backup.
spec:
  export_type: private_backup
  signals:
    - id: old-signal-id
      name: Imported unresolved stale work
      entity_type: issue
      target_scopes:
        - connector_id: old-connector-id
          scope_id: missing-scope-id
          scope_type: board
      expression:
        type: group
        operator: all
        conditions:
          - field: status_category
            operator: is
            value: in_progress
      report_settings:
        severity: warning
        category: flow
      enabled: true
      origin: imported
"""

    preview = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": raw_yaml, "mode": "additive"},
    )
    assert preview.status_code == 200
    assert preview.json()["unresolved_mappings"] == ["Imported unresolved stale work"]

    apply = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": raw_yaml, "mode": "additive"},
    )
    assert apply.status_code == 200

    imported = next(
        definition
        for definition in api_client.get("/api/signal-definitions").json()
        if definition["name"] == "Imported unresolved stale work"
    )
    assert imported["enabled"] is False
    assert imported["target_scopes"] == []
