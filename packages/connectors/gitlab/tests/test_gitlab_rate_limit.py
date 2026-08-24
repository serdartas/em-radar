"""Tests for GitLab 429 → ConnectorRateLimitedError (AUDIT-25)."""

import asyncio
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_core.connectors import ConnectorRateLimitedError


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_fetch_raises_rate_limited_error_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    monkeypatch.setattr(
        gitlab_connector_module,
        "CLIENT_FACTORY",
        _client_factory_for(handler),
    )
    connector = GitLabConnector({"base_url": "https://gitlab.example.com", "token": "token-1234"})

    async def run() -> None:
        with pytest.raises(ConnectorRateLimitedError):
            await connector.test_connection()
        await connector.close()

    asyncio.run(run())
