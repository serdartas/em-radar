import asyncio
import logging
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector, GitLabConnectorConfig
from em_radar_core.connectors import ConnectorAuthError, ConnectorConfigError


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_config_schema_declares_secret_token_and_tls_default() -> None:
    config = GitLabConnectorConfig.model_validate(
        {
            "base_url": "https://gitlab.example.com",
            "token": "gitlab-token-1234",
        }
    )
    token_schema = GitLabConnector.config_schema["properties"]["token"]

    assert config.verify_tls is True
    assert token_schema["format"] == "password"
    assert token_schema["writeOnly"] is True


def test_invalid_config_raises_typed_config_error() -> None:
    with pytest.raises(ConnectorConfigError):
        GitLabConnector({"base_url": "not-a-url", "token": "gitlab-token-1234"})


def test_connection_success_returns_user_and_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "gitlab-token-1234"

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["private-token"] == token
            if request.url.path == "/api/v4/user":
                return httpx.Response(200, json={"name": "GitLab User", "username": "gitlab-user"})
            if request.url.path == "/api/v4/personal_access_tokens/self":
                return httpx.Response(
                    200,
                    json={
                        "scopes": ["read_api", "read_user"],
                        "granular_scopes": [
                            {"permissions": ["read_repository", "read_merge_request"]}
                        ],
                    },
                )
            raise AssertionError(f"unexpected path: {request.url.path}")

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {
                "base_url": "https://gitlab.example.com",
                "token": token,
            }
        )
        result = await connector.test_connection()
        await connector.close()

        assert result.ok is True
        assert result.user_display_name == "GitLab User"
        assert result.permissions == [
            "read_api",
            "read_merge_request",
            "read_repository",
            "read_user",
        ]
        assert result.detail == "Connected to GitLab"

    asyncio.run(run())


def test_connection_raises_auth_error_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "gitlab-token-1234"

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["private-token"] == token
            return httpx.Response(401)

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {
                "base_url": "https://gitlab.example.com",
                "token": token,
            }
        )

        with pytest.raises(ConnectorAuthError):
            await connector.test_connection()

        await connector.close()

    asyncio.run(run())


def test_connection_does_not_log_token(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    token = "gitlab-token-1234"

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            logging.getLogger("httpx").debug("request headers: %s", request.headers)
            logging.getLogger("httpcore.connection").debug(
                "child logger request headers: %s", request.headers
            )
            return httpx.Response(401)

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {
                "base_url": "https://gitlab.example.com",
                "token": token,
            }
        )

        caplog.set_level(logging.DEBUG)
        with pytest.raises(ConnectorAuthError):
            await connector.test_connection()

        await connector.close()

    asyncio.run(run())

    assert any("[REDACTED]" in record.getMessage() for record in caplog.records)
    assert any(
        record.name == "httpcore.connection" and "[REDACTED]" in record.getMessage()
        for record in caplog.records
    )
    assert all(token not in record.getMessage() for record in caplog.records)


def test_connection_preserves_base_url_context_path(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_paths: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            requested_paths.append(request.url.path)
            if request.url.path == "/gitlab/api/v4/user":
                return httpx.Response(200, json={"username": "gitlab-user"})
            if request.url.path == "/gitlab/api/v4/personal_access_tokens/self":
                return httpx.Response(200, json={"scopes": ["read_api"]})
            raise AssertionError(f"unexpected path: {request.url.path}")

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {
                "base_url": "https://gitlab.example.com/gitlab",
                "token": "gitlab-token-1234",
            }
        )

        result = await connector.test_connection()
        await connector.close()

        assert result.ok is True

    asyncio.run(run())

    assert requested_paths == [
        "/gitlab/api/v4/user",
        "/gitlab/api/v4/personal_access_tokens/self",
    ]
