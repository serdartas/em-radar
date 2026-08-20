from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from em_radar_core.connectors import Capabilities, ConnectionTestResult
from em_radar_connector_jira.connector import JiraFieldInfo


class JiraFieldDiscoveryTestConnector:
    name: ClassVar[str] = "jira"
    display_name: ClassVar[str] = "Jira (Test)"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "base_url": {"type": "string"},
            "token": {"type": "string", "minLength": 1},
        },
        "required": ["base_url", "token"],
        "additionalProperties": False,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            ok=True, detail="ok", user_display_name="Test User", permissions=[]
        )

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities(provides_workitems=True)

    @classmethod
    def describe_signal_schema(cls) -> object:
        from em_radar_core.connectors import SignalCapabilitySchema

        return SignalCapabilitySchema(
            connector_type="jira", entity_types=(), scope_types=(), fields=()
        )

    async def discover_fields(self) -> list[JiraFieldInfo]:
        return [
            JiraFieldInfo(id="summary", name="Summary", custom=False, field_type="string"),
            JiraFieldInfo(
                id="customfield_10016", name="Story Points", custom=True, field_type="number"
            ),
        ]

    async def close(self) -> None:
        pass


def _create_jira_connection(api_client: TestClient) -> str:
    resp = api_client.post(
        "/api/connections",
        json={
            "name": "Test Jira",
            "connector_name": "jira",
            "config": {"base_url": "https://jira.test.invalid", "token": "tok"},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_jira_fields_returns_field_list(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraFieldDiscoveryTestConnector],
    )
    connection_id = _create_jira_connection(api_client)

    resp = api_client.get(f"/api/connections/{connection_id}/jira/fields")

    assert resp.status_code == 200
    fields = resp.json()
    ids = [f["id"] for f in fields]
    assert "summary" in ids
    assert "customfield_10016" in ids


def test_jira_fields_never_includes_token(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraFieldDiscoveryTestConnector],
    )
    connection_id = _create_jira_connection(api_client)

    resp = api_client.get(f"/api/connections/{connection_id}/jira/fields")

    assert resp.status_code == 200
    body = resp.text
    assert "tok" not in body


def test_jira_fields_returns_404_for_unknown_connection(api_client: TestClient) -> None:
    resp = api_client.get("/api/connections/00000000-0000-0000-0000-000000000099/jira/fields")
    assert resp.status_code == 404
