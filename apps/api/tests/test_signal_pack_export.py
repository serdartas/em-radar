"""Tests for signal pack export (declarative signal groups path)."""

import yaml
from fastapi.testclient import TestClient

from em_radar_config import load_signal_pack


def test_export_signal_group_produces_valid_declarative_pack(
    api_client: TestClient,
    session_factory,
) -> None:
    """Export a signal group that has at least one signal definition."""
    # Seed a signal definition and a group.
    defn_id = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Export test signal",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "status_category", "operator": "is", "value": "in_progress"}
                ],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "enabled": True,
            "origin": "user_created",
        },
    ).json()["id"]
    group_id = api_client.post(
        "/api/signal-config-groups",
        json={"name": "export-test-group", "signal_ids": [defn_id]},
    ).json()["id"]

    response = api_client.get(
        "/api/signal-pack/export",
        params={"group_ids": [group_id], "export_type": "private_backup"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/yaml")
    assert response.headers["content-disposition"] == 'attachment; filename="signal-pack.yaml"'
    pack = load_signal_pack(response.text).pack
    assert pack.metadata.name == "export-test-group"
    assert len(pack.spec.signals) == 1
    assert pack.spec.signals[0].name == "Export test signal"


def test_export_requires_group_ids(api_client: TestClient) -> None:
    response = api_client.get("/api/signal-pack/export")

    assert response.status_code == 422


def test_export_name_pattern_validated(api_client: TestClient) -> None:
    """Invalid pack names (not kebab-case) are rejected by query parameter validation."""
    response = api_client.get(
        "/api/signal-pack/export",
        params={"name": "Not Valid"},
    )

    assert response.status_code == 422


def test_export_has_no_credential_named_keys(
    api_client: TestClient,
    session_factory,
) -> None:
    defn_id = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Cred check signal",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "status_category", "operator": "is", "value": "in_progress"}
                ],
            },
            "report_settings": {"severity": "info", "category": "flow"},
            "enabled": True,
            "origin": "user_created",
        },
    ).json()["id"]
    group_id = api_client.post(
        "/api/signal-config-groups",
        json={"name": "cred-check-group", "signal_ids": [defn_id]},
    ).json()["id"]

    response = api_client.get(
        "/api/signal-pack/export",
        params={"group_ids": [group_id]},
    )

    assert response.status_code == 200
    exported = yaml.safe_load(response.text)
    assert not _credential_keys(exported)


def _credential_keys(value: object) -> set[str]:
    credential_names = {"token", "password", "api_key", "secret", "authorization"}
    if isinstance(value, dict):
        keys = {str(key).casefold() for key in value}
        return (keys & credential_names).union(
            *(_credential_keys(child) for child in value.values())
        )
    if isinstance(value, list):
        return set().union(*(_credential_keys(child) for child in value))
    return set()
