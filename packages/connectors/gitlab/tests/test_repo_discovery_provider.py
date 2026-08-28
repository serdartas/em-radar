# SPDX-License-Identifier: Apache-2.0

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import DISCOVERY_DEFAULT_WINDOW_DAYS, GitLabConnector
from em_radar_core.connectors import RepositoryActivity, RepositoryRef


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


_SINCE = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _mr_payload(
    mr_id: int,
    project_id: int,
    path_with_namespace: str,
    created_at: str,
) -> dict[str, object]:
    return {
        "id": mr_id,
        "iid": mr_id,
        "project_id": project_id,
        "title": f"MR {mr_id}",
        "state": "opened",
        "created_at": created_at,
        "updated_at": created_at,
        "references": {
            "short": f"!{mr_id}",
            "relative": f"!{mr_id}",
            "full": f"{path_with_namespace}!{mr_id}",
        },
        "web_url": f"https://gitlab.example.com/{path_with_namespace}/-/merge_requests/{mr_id}",
        "author": {"id": 1, "username": "someone", "name": "Someone"},
    }


def test_discovery_default_window_constant_is_90_days() -> None:
    assert DISCOVERY_DEFAULT_WINDOW_DAYS == 90
    # Verify the constant is usable as a timedelta offset (primary caller use-case).
    window = timedelta(days=DISCOVERY_DEFAULT_WINDOW_DAYS)
    assert window.days == 90


def test_discover_repositories_capability_is_declared() -> None:
    caps = GitLabConnector.describe_capabilities()
    assert caps.provides_repository_discovery is True


def test_discover_aggregates_mrs_per_project_single_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MRs from one member across two projects aggregate correctly."""

    async def run() -> list[RepositoryActivity]:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(1, 10, "team/alpha", "2024-03-01T10:00:00Z"),
                    _mr_payload(2, 10, "team/alpha", "2024-03-15T10:00:00Z"),
                    _mr_payload(3, 20, "team/beta", "2024-02-10T10:00:00Z"),
                ],
            )

        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.discover_repositories_by_activity(["42"], since=_SINCE, limit=10)
        await connector.close()
        return results

    results = asyncio.run(run())

    assert len(results) == 2
    # RepositoryActivity is a RepositoryRef subtype per the connector contract.
    assert all(isinstance(r, RepositoryRef) for r in results)
    alpha = next(r for r in results if r.provider_project_id == "10")
    beta = next(r for r in results if r.provider_project_id == "20")

    assert alpha.name == "alpha"
    assert alpha.path_with_namespace == "team/alpha"
    assert alpha.merge_request_count == 2
    assert alpha.contributing_member_count == 1
    assert alpha.last_activity_at == datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc)

    assert beta.merge_request_count == 1
    assert beta.contributing_member_count == 1


def test_discover_counts_distinct_contributing_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each member is counted once per project regardless of how many MRs they opened."""
    requests: list[httpx.Request] = []

    async def run() -> list[RepositoryActivity]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            author_id = request.url.params.get("author_id")
            if author_id == "1":
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": ""},
                    json=[
                        _mr_payload(1, 10, "team/alpha", "2024-03-01T00:00:00Z"),
                        _mr_payload(2, 10, "team/alpha", "2024-03-10T00:00:00Z"),
                    ],
                )
            # author_id == "2"
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(3, 10, "team/alpha", "2024-02-20T00:00:00Z"),
                ],
            )

        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.discover_repositories_by_activity(
            ["1", "2"], since=_SINCE, limit=10
        )
        await connector.close()
        return results

    results = asyncio.run(run())

    assert len(results) == 1
    activity = results[0]
    assert activity.provider_project_id == "10"
    assert activity.contributing_member_count == 2  # two distinct members
    assert activity.merge_request_count == 3  # all three MRs counted
    assert activity.last_activity_at == datetime(2024, 3, 10, 0, 0, 0, tzinfo=timezone.utc)


def test_discover_passes_created_after_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `since` datetime is forwarded as `created_after` query param."""
    requests: list[httpx.Request] = []
    since = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[])

        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        await connector.discover_repositories_by_activity(["7"], since=since, limit=5)
        await connector.close()

    asyncio.run(run())

    assert len(requests) == 1
    params = requests[0].url.params
    assert params["author_id"] == "7"
    assert params["created_after"] == since.isoformat()
    # scope=all is required or the endpoint only returns the token owner's MRs.
    assert params["scope"] == "all"


def test_discover_results_ordered_strongest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Results are ranked: contributing_member_count desc, mr_count desc, last_activity_at desc.

    Member count is the *primary* key: a repo with more members but fewer MRs must outrank a
    repo with fewer members but more MRs, so this fails if the sort keys are transposed.
    """

    async def run() -> list[RepositoryActivity]:
        def handler(request: httpx.Request) -> httpx.Response:
            author_id = request.url.params.get("author_id")
            if author_id == "1":
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": ""},
                    json=[
                        # project 10: member 1 contributes 1 MR (member 2 adds another below).
                        _mr_payload(1, 10, "team/alpha", "2024-03-20T00:00:00Z"),
                        # project 20: member 1 alone, 5 MRs — more MRs, but only 1 member.
                        _mr_payload(2, 20, "team/beta", "2024-03-01T00:00:00Z"),
                        _mr_payload(3, 20, "team/beta", "2024-03-02T00:00:00Z"),
                        _mr_payload(4, 20, "team/beta", "2024-03-03T00:00:00Z"),
                        _mr_payload(5, 20, "team/beta", "2024-03-04T00:00:00Z"),
                        _mr_payload(6, 20, "team/beta", "2024-03-05T00:00:00Z"),
                        # project 30: member 1 alone, 1 MR.
                        _mr_payload(7, 30, "team/gamma", "2024-03-01T00:00:00Z"),
                    ],
                )
            # author_id == "2": second contributor to project 10 only.
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(8, 10, "team/alpha", "2024-02-28T00:00:00Z"),
                ],
            )

        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.discover_repositories_by_activity(
            ["1", "2"], since=_SINCE, limit=10
        )
        await connector.close()
        return results

    results = asyncio.run(run())

    # project 10: 2 members, 2 MRs → strongest (member count is the primary key)
    # project 20: 1 member, 5 MRs → second (fewer members, even though more MRs)
    # project 30: 1 member, 1 MR → last (member tie with 20 broken by MR count)
    assert len(results) == 3
    assert [r.provider_project_id for r in results] == ["10", "20", "30"]
    assert results[0].contributing_member_count == 2
    assert results[0].merge_request_count == 2
    assert results[1].contributing_member_count == 1
    assert results[1].merge_request_count == 5


def test_discover_respects_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Results are capped at `limit` after ranking."""

    async def run() -> list[RepositoryActivity]:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(i, i + 100, f"team/proj-{i}", f"2024-0{(i % 3) + 1}-01T00:00:00Z")
                    for i in range(1, 6)
                ],
            )

        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.discover_repositories_by_activity(["42"], since=_SINCE, limit=3)
        await connector.close()
        return results

    results = asyncio.run(run())
    assert len(results) == 3


def test_discover_returns_empty_when_no_mrs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> list[RepositoryActivity]:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"X-Next-Page": ""}, json=[])

        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.discover_repositories_by_activity(
            ["1", "2"], since=_SINCE, limit=10
        )
        await connector.close()
        return results

    assert asyncio.run(run()) == []


def test_discover_paginates_member_mrs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All pages are fetched for each member."""
    requests: list[httpx.Request] = []

    async def run() -> list[RepositoryActivity]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            page = int(request.url.params.get("page", "1"))
            # Return PAGE_SIZE items on page 1 to trigger pagination, fewer on page 2.
            if page == 1:
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": "2"},
                    json=[
                        _mr_payload(i, 10, "team/alpha", "2024-03-01T00:00:00Z")
                        for i in range(1, 101)
                    ],
                )
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    _mr_payload(101, 10, "team/alpha", "2024-03-15T00:00:00Z"),
                ],
            )

        monkeypatch.setattr(gitlab_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.discover_repositories_by_activity(["5"], since=_SINCE, limit=10)
        await connector.close()
        return results

    results = asyncio.run(run())

    assert len(results) == 1
    assert results[0].merge_request_count == 101
    assert len(requests) == 2  # two pages fetched
