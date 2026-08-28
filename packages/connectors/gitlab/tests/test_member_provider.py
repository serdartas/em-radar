# SPDX-License-Identifier: Apache-2.0

import asyncio
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_core.connectors import ConnectorAuthError, MemberRef


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


_USER_PAYLOAD = {
    "id": 42,
    "username": "mustapha",
    "name": "Mustapha Kaya",
    "avatar_url": "https://gitlab.example.com/uploads/user/avatar/42/avatar.png",
}


def test_search_users_issues_bounded_query_and_maps_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    async def run() -> list[MemberRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_USER_PAYLOAD],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_users("musta", limit=20)
        await connector.close()
        return results

    results = asyncio.run(run())

    assert len(results) == 1
    member = results[0]
    assert member.provider_user_id == "42"
    assert member.username == "mustapha"
    assert member.display_name == "Mustapha Kaya"
    assert member.avatar_url == "https://gitlab.example.com/uploads/user/avatar/42/avatar.png"

    assert len(requests) == 1
    params = requests[0].url.params
    assert params["search"] == "musta"
    assert int(params["per_page"]) == 20


def test_get_user_maps_single_user(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> MemberRef | None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v4/users/42"
            return httpx.Response(200, json=_USER_PAYLOAD)

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        result = await connector.get_user("42")
        await connector.close()
        return result

    result = asyncio.run(run())

    assert result is not None
    assert result.provider_user_id == "42"
    assert result.username == "mustapha"
    assert result.display_name == "Mustapha Kaya"


def test_get_user_returns_none_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> MemberRef | None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        result = await connector.get_user("99999")
        await connector.close()
        return result

    assert asyncio.run(run()) is None


def test_get_user_raises_auth_error_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        with pytest.raises(ConnectorAuthError):
            await connector.get_user("42")
        await connector.close()

    asyncio.run(run())


def test_search_users_raises_auth_error_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        with pytest.raises(ConnectorAuthError):
            await connector.search_users("musta", limit=10)
        await connector.close()

    asyncio.run(run())


def test_search_users_returns_empty_list_when_no_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> list[MemberRef]:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[])

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_users("zzznomatch", limit=20)
        await connector.close()
        return results

    assert asyncio.run(run()) == []


def test_search_users_accumulates_pages_and_caps_per_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def _user(user_id: int) -> dict[str, object]:
        return {
            "id": user_id,
            "username": f"user{user_id}",
            "name": f"User {user_id}",
            "avatar_url": None,
        }

    async def run() -> list[MemberRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            page = int(request.url.params["page"])
            if page == 1:
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": "2"},
                    json=[_user(i) for i in range(1, 101)],
                )
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_user(i) for i in range(101, 151)],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_users("user", limit=150)
        await connector.close()
        return results

    results = asyncio.run(run())

    assert len(results) == 150
    # per_page is capped at GitLab's maximum, so the 150 results span two pages.
    assert int(requests[0].url.params["per_page"]) == 100
    assert [r.provider_user_id for r in results[:3]] == ["1", "2", "3"]


def test_member_provider_capability_is_declared() -> None:
    caps = GitLabConnector.describe_capabilities()
    assert caps.provides_members is True


def test_search_users_avatar_url_can_be_none(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> list[MemberRef]:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    {
                        "id": 7,
                        "username": "noavatar",
                        "name": "No Avatar User",
                        "avatar_url": None,
                    }
                ],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_users("noavatar", limit=5)
        await connector.close()
        return results

    results = asyncio.run(run())
    assert len(results) == 1
    assert results[0].avatar_url is None
