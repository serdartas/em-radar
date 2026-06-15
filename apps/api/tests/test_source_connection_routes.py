from fastapi.testclient import TestClient
from typing import ClassVar

from em_radar_core.connectors import Capabilities, ConnectionTestResult


class JiraTestConnector:
    name: ClassVar[str] = "jira"
    display_name: ClassVar[str] = "Jira"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "base_url": {"type": "string"},
            "token": {"type": "string", "minLength": 20},
        },
        "required": ["base_url", "token"],
        "additionalProperties": False,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            ok=True,
            detail="Connected",
            user_display_name="Ada Lovelace",
            permissions=["read"],
        )

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities()

    async def close(self) -> None:
        pass


def test_source_connection_routes_crud_test_and_preserve_omitted_config(
    api_client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    created_response = api_client.post(
        "/api/connections",
        json={
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["config"] == {
        "base_url": "https://demo.invalid",
        "token": "****6789",
    }

    assert api_client.get("/api/connections").json() == [created]

    test_response = api_client.post(f"/api/connections/{created['id']}/test")
    assert test_response.status_code == 200
    assert test_response.json() == {
        "ok": True,
        "detail": "Connected",
        "user_display_name": "Ada Lovelace",
        "permissions": ["read"],
    }

    updated_response = api_client.patch(
        f"/api/connections/{created['id']}",
        json={"config": {"base_url": "https://updated.invalid"}},
    )
    assert updated_response.status_code == 200
    assert updated_response.json()["config"] == {
        "base_url": "https://updated.invalid",
        "token": "****6789",
    }

    assert api_client.delete(f"/api/connections/{created['id']}").status_code == 204
    assert api_client.get("/api/connections").json() == []


def test_source_connection_draft_test_returns_token_free_failure(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/connections/test",
        json={"connector_name": "demo", "config": {"unexpected": "secret-token"}},
    )

    assert response.status_code == 200
    assert not response.json()["ok"]
    assert "secret-token" not in response.json()["detail"]
