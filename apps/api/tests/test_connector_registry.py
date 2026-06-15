from typing import ClassVar

import pytest

from em_radar_api.connector_registry import create_connector, list_connectors
from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorBase,
    ConnectorConfigError,
    ConnectorError,
    ConnectorNotFoundError,
)


class ConfiguredConnector:
    name: ClassVar[str] = "configured"
    display_name: ClassVar[str] = "Configured"
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
        if "token" not in config:
            raise ValueError("token is required")
        self.config = config

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="Connected")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities(provides_workitems=True)

    async def close(self) -> None:
        pass


def test_get_connectors_includes_demo_with_schema_and_capabilities(api_client) -> None:
    response = api_client.get("/api/connectors")

    assert response.status_code == 200
    demo = next(connector for connector in response.json() if connector["name"] == "demo")
    assert demo == {
        "name": "demo",
        "display_name": "Demo company",
        "config_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "capabilities": {
            "provides_workitems": True,
            "provides_sprints": True,
            "provides_mergerequests": True,
            "provides_repositories": True,
            "provides_reviews": True,
            "provides_comments": True,
            "provides_transitions": True,
            "supports_incremental_fetch": False,
            "supports_pagination_cursor": False,
            "max_window_days": None,
        },
    }


def test_registry_flags_secrets_and_factory_validates_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [ConfiguredConnector],
    )

    descriptor = list_connectors()[0]
    connector = create_connector(
        "configured",
        {"base_url": "https://example.com", "token": "valid-secret-12345678"},
    )

    assert descriptor["config_schema"]["properties"]["token"]["writeOnly"] is True
    assert descriptor["capabilities"]["provides_workitems"] is True
    assert isinstance(connector, ConnectorBase)
    assert connector.config == {
        "base_url": "https://example.com",
        "token": "valid-secret-12345678",
    }

    with pytest.raises(ConnectorConfigError):
        create_connector("configured", {"base_url": "https://example.com"})

    with pytest.raises(ConnectorConfigError) as error:
        create_connector(
            "configured",
            {"base_url": "https://example.com", "token": "short-secret"},
        )
    assert "short-secret" not in str(error.value)

    with pytest.raises(ConnectorNotFoundError):
        create_connector("missing", {})


def test_registry_rejects_connector_requiring_newer_model_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IncompatibleConnector(ConfiguredConnector):
        name = "incompatible"
        min_model_version = 2

    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [IncompatibleConnector],
    )

    with pytest.raises(ConnectorError, match="upgrade EM Radar"):
        list_connectors()

    with pytest.raises(ConnectorError, match="upgrade EM Radar"):
        create_connector("incompatible", {})
