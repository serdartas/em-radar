# SPDX-License-Identifier: Apache-2.0

import asyncio
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_core.connectors import ConnectorAuthError, GroupRef, MemberRef


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


_GROUP_PAYLOAD = {
    "id": 7,
    "name": "Frontend",
    "full_path": "acme/frontend",
}

_MEMBER_PAYLOAD = {
    "id": 42,
    "username": "mustapha",
    "name": "Mustapha Kaya",
    "avatar_url": "https://gitlab.example.com/uploads/user/avatar/42/avatar.png",
}


# ---------------------------------------------------------------------------
# search_groups — maps results and is bounded
# ---------------------------------------------------------------------------


def test_search_groups_maps_results(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    async def run() -> list[GroupRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_GROUP_PAYLOAD],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_groups("frontend", limit=20)
        await connector.close()
        return results

    results = asyncio.run(run())

    assert len(results) == 1
    group = results[0]
    assert group.provider_group_id == "7"
    assert group.name == "Frontend"
    assert group.full_path == "acme/frontend"

    assert len(requests) == 1
    params = requests[0].url.params
    assert params["search"] == "frontend"
    assert int(params["per_page"]) == 20


def test_search_groups_is_bounded_by_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def _group(group_id: int) -> dict[str, object]:
        return {"id": group_id, "name": f"Group {group_id}", "full_path": f"acme/group{group_id}"}

    async def run() -> list[GroupRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            # Return 5 groups per page, always signal more
            return httpx.Response(
                200,
                headers={"X-Next-Page": "2"},
                json=[_group(i) for i in range(1, 6)],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_groups("group", limit=3)
        await connector.close()
        return results

    results = asyncio.run(run())

    # Limit=3 so only the first 3 are returned; per_page is capped at limit=3.
    assert len(results) == 3
    assert int(requests[0].url.params["per_page"]) == 3


def test_search_groups_accumulates_across_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    def _group(group_id: int) -> dict[str, object]:
        return {"id": group_id, "name": f"G{group_id}", "full_path": f"a/g{group_id}"}

    async def run() -> list[GroupRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params["page"])
            if page == 1:
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": "2"},
                    json=[_group(i) for i in range(1, 101)],
                )
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_group(i) for i in range(101, 151)],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_groups("g", limit=150)
        await connector.close()
        return results

    results = asyncio.run(run())
    assert len(results) == 150


def test_search_groups_raises_auth_error_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
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
            await connector.search_groups("any", limit=10)
        await connector.close()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# list_group_members — maps members, paginates, and 403 → auth error
# ---------------------------------------------------------------------------


def test_list_group_members_maps_members(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    async def run() -> list[MemberRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_MEMBER_PAYLOAD],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.list_group_members("7", limit=20)
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
    # Numeric group id — not URL-encoded (just the digit string).
    assert requests[0].url.path == "/api/v4/groups/7/members"


def test_list_group_members_accepts_slash_separated_namespace_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    async def run() -> list[MemberRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[])

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.list_group_members("acme/frontend", limit=10)
        await connector.close()
        return results

    asyncio.run(run())
    # httpx normalises percent-encoded slashes back to "/" before sending, so the
    # slash-separated namespace path appears as-is in the URL path that reaches
    # the mock transport. GitLab accepts both numeric IDs and namespace paths.
    assert requests[0].url.path == "/api/v4/groups/acme/frontend/members"


def test_list_group_members_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    def _member(user_id: int) -> dict[str, object]:
        return {
            "id": user_id,
            "username": f"user{user_id}",
            "name": f"User {user_id}",
            "avatar_url": None,
        }

    async def run() -> list[MemberRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params["page"])
            if page == 1:
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": "2"},
                    json=[_member(i) for i in range(1, 101)],
                )
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_member(i) for i in range(101, 141)],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.list_group_members("7", limit=140)
        await connector.close()
        return results

    results = asyncio.run(run())
    assert len(results) == 140
    assert results[0].provider_user_id == "1"
    assert results[100].provider_user_id == "101"


def test_list_group_members_403_raises_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
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
            await connector.list_group_members("7", limit=10)
        await connector.close()

    asyncio.run(run())


def test_list_group_members_capped_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def _member(user_id: int) -> dict[str, object]:
        return {"id": user_id, "username": f"u{user_id}", "name": f"U{user_id}", "avatar_url": None}

    async def run() -> list[MemberRef]:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"X-Next-Page": "2"},
                json=[_member(i) for i in range(1, 11)],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.list_group_members("7", limit=5)
        await connector.close()
        return results

    results = asyncio.run(run())
    assert len(results) == 5
