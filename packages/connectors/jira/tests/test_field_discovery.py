import asyncio
from collections.abc import Callable

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import JiraConnector

_FIELD_PAYLOAD = [
    {
        "id": "customfield_10016",
        "name": "Story Points",
        "custom": True,
        "schema": {
            "type": "number",
            "custom": "com.atlassian.jira.plugin.system.customfieldtypes:float",
        },
    },
    {
        "id": "summary",
        "name": "Summary",
        "custom": False,
        "schema": {"type": "string", "system": "summary"},
    },
    {
        "id": "assignee",
        "name": "Assignee",
        "custom": False,
        "schema": {"type": "user", "system": "assignee"},
    },
    {
        "id": "customfield_10100",
        "name": "acceptance criteria",
        "custom": True,
        "schema": {"type": "string"},
    },
]


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_discover_fields_returns_normalized_sorted_list(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    async def run() -> None:
        nonlocal call_count

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            if request.url.path == "/rest/api/3/field":
                call_count += 1
                return httpx.Response(200, json=_FIELD_PAYLOAD)
            raise AssertionError(f"unexpected path: {request.url.path}")

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {"base_url": "https://jira.example.com", "token": "tok", "auth_email": "u@x.com"}
        )

        fields = await connector.discover_fields()
        await connector.close()

        names = [f.name for f in fields]
        assert names == sorted(names, key=str.lower)
        assert any(
            f.id == "customfield_10016" and f.custom and f.field_type == "number" for f in fields
        )
        assert any(f.id == "summary" and not f.custom and f.field_type == "string" for f in fields)
        assert call_count == 1

    asyncio.run(run())


def test_discover_fields_caches_result(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    async def run() -> None:
        nonlocal call_count

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            if request.url.path == "/rest/api/3/field":
                call_count += 1
                return httpx.Response(200, json=_FIELD_PAYLOAD)
            raise AssertionError(f"unexpected path: {request.url.path}")

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {"base_url": "https://jira.example.com", "token": "tok", "auth_email": "u@x.com"}
        )

        first = await connector.discover_fields()
        second = await connector.discover_fields()
        await connector.close()

        assert first is second
        assert call_count == 1

    asyncio.run(run())


def test_discover_fields_includes_type_info(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/rest/api/3/field":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "cf_num",
                            "name": "A Number",
                            "custom": True,
                            "schema": {"type": "number"},
                        },
                        {
                            "id": "cf_txt",
                            "name": "A Text",
                            "custom": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "id": "cf_opt",
                            "name": "A Select",
                            "custom": True,
                            "schema": {"type": "option"},
                        },
                        {"id": "cf_noscm", "name": "No Schema", "custom": True},
                    ],
                )
            raise AssertionError(f"unexpected path: {request.url.path}")

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {"base_url": "https://jira.example.com", "token": "tok", "auth_email": "u@x.com"}
        )
        fields = await connector.discover_fields()
        await connector.close()

        by_id = {f.id: f for f in fields}
        assert by_id["cf_num"].field_type == "number"
        assert by_id["cf_txt"].field_type == "string"
        assert by_id["cf_opt"].field_type == "option"
        assert by_id["cf_noscm"].field_type is None

    asyncio.run(run())
