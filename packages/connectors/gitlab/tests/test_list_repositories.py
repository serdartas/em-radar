import asyncio
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_core.models import Source


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_list_repositories_normalizes_all_paginated_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            page = request.url.params["page"]
            if page == "1":
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": "2"},
                    json=[
                        {
                            "id": 101,
                            "name": "API",
                            "path_with_namespace": "engineering/platform/api",
                            "default_branch": "main",
                            "archived": False,
                            "web_url": "https://gitlab.example.com/engineering/platform/api",
                        },
                        {
                            "id": 102,
                            "name": "Legacy",
                            "path_with_namespace": "engineering/legacy",
                            "default_branch": "master",
                            "archived": True,
                            "web_url": "https://gitlab.example.com/engineering/legacy",
                        },
                    ],
                )
            if page == "2":
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": ""},
                    json=[
                        {
                            "id": 103,
                            "name": "Web",
                            "path_with_namespace": "product/web",
                            "default_branch": "trunk",
                            "archived": False,
                            "web_url": "https://gitlab.example.com/product/web",
                        }
                    ],
                )
            raise AssertionError(f"unexpected page: {page}")

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {
                "base_url": "https://gitlab.example.com",
                "token": "gitlab-token-1234",
            }
        )

        repositories = await connector.list_repositories()
        await connector.close()

        assert [
            (
                repository.external_id,
                repository.name,
                repository.full_path,
                repository.default_branch,
                repository.is_archived,
            )
            for repository in repositories
        ] == [
            ("101", "API", "engineering/platform/api", "main", False),
            ("102", "Legacy", "engineering/legacy", "master", True),
            ("103", "Web", "product/web", "trunk", False),
        ]
        assert all(repository.source is Source.GITLAB for repository in repositories)
        assert repositories[0].source_url == ("https://gitlab.example.com/engineering/platform/api")

    asyncio.run(run())

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert all(request.url.params["per_page"] == "100" for request in requests)
    assert all(request.url.params["order_by"] == "id" for request in requests)
    assert all(request.url.params["sort"] == "asc" for request in requests)
    assert all("membership" not in request.url.params for request in requests)
    assert all("archived" not in request.url.params for request in requests)


def test_list_repositories_keeps_projects_without_a_default_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[
                    {
                        "id": 104,
                        "name": "Empty",
                        "path_with_namespace": "sandbox/empty",
                        "default_branch": None,
                        "archived": False,
                        "web_url": "https://gitlab.example.com/sandbox/empty",
                    }
                ],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {
                "base_url": "https://gitlab.example.com",
                "token": "gitlab-token-1234",
            }
        )

        repositories = await connector.list_repositories()
        await connector.close()

        assert len(repositories) == 1
        assert repositories[0].default_branch == ""

    asyncio.run(run())
