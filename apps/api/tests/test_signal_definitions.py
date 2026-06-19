from fastapi.testclient import TestClient


def _definition_payload(scope_id: str | None = "scope-1") -> dict[str, object]:
    return {
        "name": "Stale platform work",
        "description": "Finds stale Jira issues.",
        "entity_type": "issue",
        "target_scopes": (
            [{"connector_id": "conn-1", "scope_id": scope_id, "scope_type": "board"}]
            if scope_id is not None
            else []
        ),
        "expression": {
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "status_category", "operator": "is", "value": "in_progress"}],
        },
        "report_settings": {"severity": "warning", "category": "flow"},
        "enabled": True,
        "origin": "user_created",
        "template_key": None,
    }


def test_duplicate_signal_names_are_rejected(api_client: TestClient) -> None:
    response = api_client.post("/api/signal-definitions", json=_definition_payload())
    assert response.status_code == 201

    duplicate = api_client.post("/api/signal-definitions", json=_definition_payload("scope-2"))
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "signal name must be unique"


def test_enabled_signals_require_target_scopes(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/signal-definitions",
        json=_definition_payload(scope_id=None),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "enabled signals require at least one target scope"


def test_disabled_imported_signals_may_be_stored_unmapped(api_client: TestClient) -> None:
    payload = _definition_payload(scope_id=None)
    payload["enabled"] = False
    payload["origin"] = "imported"
    response = api_client.post("/api/signal-definitions", json=payload)

    assert response.status_code == 201
    created = response.json()
    assert created["enabled"] is False
    assert created["target_scopes"] == []
    assert created["origin"] == "imported"


def test_version_increments_on_update(api_client: TestClient) -> None:
    create_response = api_client.post("/api/signal-definitions", json=_definition_payload())
    assert create_response.status_code == 201
    created = create_response.json()

    update_response = api_client.patch(
        f"/api/signal-definitions/{created['id']}",
        json={"description": "Updated description."},
    )

    assert update_response.status_code == 200
    assert update_response.json()["version"] == created["version"] + 1
