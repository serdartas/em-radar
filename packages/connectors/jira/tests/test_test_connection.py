import asyncio
import logging
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.connectors import ConnectorAuthError


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_connection_success_returns_user_and_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "jira-token-1234"
    expected_authorization = "Basic amlyYS5lbWFpbEBleGFtcGxlLmNvbTpqaXJhLXRva2VuLTEyMzQ="

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == expected_authorization
            if request.url.path == "/rest/api/2/myself":
                return httpx.Response(200, json={"displayName": "Jira User"})
            if request.url.path == "/rest/api/2/mypermissions":
                return httpx.Response(
                    200,
                    json={
                        "permissions": {
                            "BROWSE_PROJECTS": {"havePermission": True},
                            "EDIT_ISSUES": {"havePermission": False},
                            "ADMINISTER": {"havePermission": True},
                        }
                    },
                )
            raise AssertionError(f"unexpected path: {request.url.path}")

        monkeypatch.setattr(
            jira_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": token,
                "auth_email": "jira.email@example.com",
            }
        )
        result = await connector.test_connection()
        await connector.close()

        assert result.ok is True
        assert result.user_display_name == "Jira User"
        assert result.permissions == ["ADMINISTER", "BROWSE_PROJECTS"]
        assert result.detail == "Connected to Jira"

    asyncio.run(run())


def test_connection_preserves_base_url_context_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_paths: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path == "/jira/rest/api/2/myself":
                return httpx.Response(200, json={"name": "jira-user"})
            if request.url.path == "/jira/rest/api/2/mypermissions":
                return httpx.Response(200, json={"permissions": {}})
            raise AssertionError(f"unexpected path: {request.url.path}")

        monkeypatch.setattr(
            jira_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com/jira",
                "token": "jira-token-1234",
            }
        )

        await connector.test_connection()
        await connector.close()

    asyncio.run(run())

    assert seen_paths == ["/jira/rest/api/2/myself", "/jira/rest/api/2/mypermissions"]


def test_capabilities_match_m3_01_connection_test_only_scope() -> None:
    capabilities = JiraConnector.describe_capabilities()

    assert capabilities.provides_workitems is False
    assert capabilities.provides_sprints is False
    assert capabilities.provides_transitions is False
    assert capabilities.supports_incremental_fetch is False


def test_connection_raises_auth_error_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "jira-token-1234"

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(401)

        monkeypatch.setattr(
            jira_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": token,
                "auth_email": "jira.email@example.com",
            }
        )

        with pytest.raises(ConnectorAuthError):
            await connector.test_connection()

        await connector.close()

    asyncio.run(run())


def test_connection_does_not_log_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    token = "jira-token-1234"

    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401)

        monkeypatch.setattr(
            jira_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": token,
                "auth_email": "jira.email@example.com",
            }
        )

        caplog.set_level(logging.DEBUG)
        with pytest.raises(ConnectorAuthError):
            await connector.test_connection()

        await connector.close()

    asyncio.run(run())

    assert all(token not in record.getMessage() for record in caplog.records)
