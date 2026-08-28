# SPDX-License-Identifier: Apache-2.0

import asyncio
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_gitlab.connector as gitlab_connector_module
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_core.connectors import ConnectorAuthError, ConnectorDataError, RepositoryRef
from em_radar_core.models import Repository


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


_PROJECT_PAYLOAD: dict[str, object] = {
    "id": 17,
    "name": "fraud-detection",
    "path_with_namespace": "risk/fraud-detection",
    "web_url": "https://gitlab.example.com/risk/fraud-detection",
}


def test_search_projects_issues_bounded_query_and_maps_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    async def run() -> list[RepositoryRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_PROJECT_PAYLOAD],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_projects("fraud", limit=20)
        await connector.close()
        return results

    results = asyncio.run(run())

    assert len(results) == 1
    project = results[0]
    assert project.provider_project_id == "17"
    assert project.name == "fraud-detection"
    assert project.path_with_namespace == "risk/fraud-detection"

    assert len(requests) == 1
    params = requests[0].url.params
    assert params["search"] == "fraud"
    assert int(params["per_page"]) == 20
    assert params["order_by"] == "id"
    # search_namespaces lets a namespace / full-path query resolve, not only the bare name.
    assert params["search_namespaces"] == "true"
    # membership keeps discovery scoped to projects reachable through the connection.
    assert params["membership"] == "true"


def test_search_projects_raises_on_non_advancing_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"X-Next-Page": "1"},
                json=[
                    {
                        "id": 1,
                        "name": "a",
                        "path_with_namespace": "ns/a",
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
        with pytest.raises(ConnectorDataError):
            await connector.search_projects("loop", limit=50)
        await connector.close()

    asyncio.run(run())


def test_get_project_maps_single_project(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> RepositoryRef | None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v4/projects/17"
            return httpx.Response(200, json=_PROJECT_PAYLOAD)

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        result = await connector.get_project("17")
        await connector.close()
        return result

    result = asyncio.run(run())

    assert result is not None
    assert result.provider_project_id == "17"
    assert result.name == "fraud-detection"
    assert result.path_with_namespace == "risk/fraud-detection"


def test_get_project_returns_none_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> RepositoryRef | None:
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
        result = await connector.get_project("99999")
        await connector.close()
        return result

    assert asyncio.run(run()) is None


def test_get_project_raises_auth_error_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
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
            await connector.get_project("17")
        await connector.close()

    asyncio.run(run())


def test_search_projects_raises_auth_error_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
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
            await connector.search_projects("fraud", limit=10)
        await connector.close()

    asyncio.run(run())


def test_search_projects_accumulates_pages_and_caps_per_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def _project(project_id: int) -> dict[str, object]:
        return {
            "id": project_id,
            "name": f"project-{project_id}",
            "path_with_namespace": f"group/project-{project_id}",
        }

    async def run() -> list[RepositoryRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            page = int(request.url.params["page"])
            if page == 1:
                return httpx.Response(
                    200,
                    headers={"X-Next-Page": "2"},
                    json=[_project(i) for i in range(1, 101)],
                )
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_project(i) for i in range(101, 151)],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_projects("project", limit=150)
        await connector.close()
        return results

    results = asyncio.run(run())

    assert len(results) == 150
    # per_page is capped at GitLab's maximum (100), so 150 results span two pages.
    assert int(requests[0].url.params["per_page"]) == 100
    assert [r.provider_project_id for r in results[:3]] == ["1", "2", "3"]


def test_repository_search_provider_capability_is_declared() -> None:
    caps = GitLabConnector.describe_capabilities()
    assert caps.provides_projects is True


def test_search_projects_returns_empty_list_when_no_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> list[RepositoryRef]:
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
        results = await connector.search_projects("zzznomatch", limit=20)
        await connector.close()
        return results

    assert asyncio.run(run()) == []


def test_search_projects_page_param_starts_at_given_page(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    async def run() -> list[RepositoryRef]:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={"X-Next-Page": ""},
                json=[_PROJECT_PAYLOAD],
            )

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        results = await connector.search_projects("fraud", limit=20, page=2)
        await connector.close()
        return results

    asyncio.run(run())

    assert len(requests) == 1
    assert requests[0].url.params["page"] == "2"


_REPOSITORY_PAYLOAD: dict[str, object] = {
    "id": 17,
    "name": "fraud-detection",
    "path_with_namespace": "risk/fraud-detection",
    "web_url": "https://gitlab.example.com/risk/fraud-detection",
    "default_branch": "main",
    "archived": False,
}


def test_get_repository_maps_project_payload_to_namespaced_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> Repository | None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v4/projects/17"
            return httpx.Response(200, json=_REPOSITORY_PAYLOAD)

        monkeypatch.setattr(
            gitlab_connector_module,
            "CLIENT_FACTORY",
            _client_factory_for(handler),
        )
        connector = GitLabConnector(
            {"base_url": "https://gitlab.example.com", "token": "gitlab-token-1234"}
        )
        result = await connector.get_repository("17")
        await connector.close()
        return result

    result = asyncio.run(run())

    assert result is not None
    assert result.external_id == "gitlab.example.com/17"
    assert result.name == "fraud-detection"
    assert result.full_path == "risk/fraud-detection"
    assert result.default_branch == "main"
    assert result.is_archived is False


def test_get_repository_returns_none_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> Repository | None:
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
        result = await connector.get_repository("99999")
        await connector.close()
        return result

    assert asyncio.run(run()) is None


def test_get_repository_raises_auth_error_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
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
            await connector.get_repository("17")
        await connector.close()

    asyncio.run(run())
