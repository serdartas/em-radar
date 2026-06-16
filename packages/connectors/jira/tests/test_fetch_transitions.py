import asyncio
from collections.abc import Callable, Mapping

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.models import EntityType, StatusCategory, Transition


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_fetch_transitions_normalizes_changelog_status_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_paths: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path == "/rest/api/2/status":
                return httpx.Response(
                    200,
                    json=[
                        _status("1", "To Do", "new"),
                        _status("2", "In Progress", "indeterminate"),
                        _status("3", "Blocked", "indeterminate"),
                        _status("4", "Done", "done"),
                    ],
                )
            if request.url.path == "/rest/api/2/issue/10002":
                assert request.url.params["fields"] == "key"
                return httpx.Response(200, json={"id": "10002", "key": "ENG-2"})
            if request.url.path == "/rest/api/2/issue/10002/changelog":
                assert request.url.params["startAt"] == "0"
                assert request.url.params["maxResults"] == "50"
                return httpx.Response(
                    200,
                    json={
                        "startAt": 0,
                        "maxResults": 50,
                        "total": 3,
                        "values": [
                            _history(
                                "102",
                                "2026-06-03T11:00:00.000+0200",
                                {"accountId": "user-2", "displayName": "Grace"},
                                [
                                    _status_item("2", "In Progress", "3", "Blocked"),
                                ],
                            ),
                            _history(
                                "101",
                                "2026-06-01T09:00:00.000Z",
                                {"accountId": "user-1", "displayName": "Ada"},
                                [
                                    _field_item("assignee", None, None, "user-1", "Ada"),
                                    _status_item(None, None, "1", "To Do"),
                                ],
                            ),
                            _history(
                                "103",
                                "2026-06-05T12:30:00.000Z",
                                None,
                                [_status_item("3", "Blocked", "4", "Done")],
                            ),
                        ],
                    },
                )
            raise AssertionError(f"unexpected request: {request.url}")

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        transitions = await _collect(connector.fetch_transitions("workitem", ["10002"]))
        await connector.close()

        assert [transition.to_status for transition in transitions] == [
            "To Do",
            "Blocked",
            "Done",
        ]
        assert [transition.from_status for transition in transitions] == [
            None,
            "In Progress",
            "Blocked",
        ]
        assert [transition.to_status_category for transition in transitions] == [
            StatusCategory.TODO,
            StatusCategory.BLOCKED,
            StatusCategory.DONE,
        ]
        assert [transition.from_status_category for transition in transitions] == [
            None,
            StatusCategory.IN_PROGRESS,
            StatusCategory.BLOCKED,
        ]
        assert transitions[0].actor_id == jira_connector_module._stable_id("user", "user-1")
        assert transitions[1].actor_id == jira_connector_module._stable_id("user", "user-2")
        assert transitions[2].actor_id is None
        assert {transition.entity_type for transition in transitions} == {EntityType.WORKITEM}
        assert {transition.entity_id for transition in transitions} == {
            jira_connector_module._stable_id("workitem", "ENG-2")
        }
        assert all(isinstance(transition, Transition) for transition in transitions)

    asyncio.run(run())

    assert seen_paths == [
        "/rest/api/2/status",
        "/rest/api/2/issue/10002",
        "/rest/api/2/issue/10002/changelog",
    ]


async def _collect(iterator: object) -> list[Transition]:
    transitions: list[Transition] = []
    async for transition in iterator:
        transitions.append(transition)
    return transitions


def _status(status_id: str, name: str, category: str) -> Mapping[str, object]:
    return {
        "id": status_id,
        "name": name,
        "statusCategory": {"key": category},
    }


def _history(
    history_id: str,
    created: str,
    author: Mapping[str, object] | None,
    items: list[Mapping[str, object]],
) -> Mapping[str, object]:
    payload: dict[str, object] = {
        "id": history_id,
        "created": created,
        "items": items,
    }
    if author is not None:
        payload["author"] = author
    return payload


def _status_item(
    from_id: str | None,
    from_status: str | None,
    to_id: str,
    to_status: str,
) -> Mapping[str, object]:
    return _field_item("status", from_id, from_status, to_id, to_status)


def _field_item(
    field: str,
    from_id: str | None,
    from_value: str | None,
    to_id: str,
    to_value: str,
) -> Mapping[str, object]:
    item: dict[str, object] = {
        "field": field,
        "to": to_id,
        "toString": to_value,
    }
    if from_id is not None:
        item["from"] = from_id
    if from_value is not None:
        item["fromString"] = from_value
    return item
