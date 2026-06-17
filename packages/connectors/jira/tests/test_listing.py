import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.models import BoardType, Source, SprintState


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_list_projects_uses_server_endpoint_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_paths: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "10000",
                        "key": "ENG",
                        "name": "Engineering",
                        "self": "https://jira.example.com/jira/rest/api/2/project/10000",
                    },
                    {
                        "id": "10001",
                        "key": "OPS",
                        "name": "Operations",
                        "self": "https://jira.example.com/jira/rest/api/2/project/10001",
                    },
                ],
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com/jira",
                "token": "jira-token-1234",
                "auth_email": "jira.email@example.com",
            }
        )

        projects = await connector.list_projects()
        await connector.close()

        assert [project.external_id for project in projects] == ["10000", "10001"]
        assert [project.key for project in projects] == ["ENG", "OPS"]
        assert projects[0].name == "Engineering"
        assert projects[0].source == Source.JIRA
        assert projects[0].source_url == "https://jira.example.com/jira/browse/ENG"
        assert projects[0].source_metadata == {
            "self": "https://jira.example.com/jira/rest/api/2/project/10000"
        }
        assert projects[0].id != projects[1].id

    asyncio.run(run())

    assert seen_paths == ["/jira/rest/api/2/project"]


def test_list_boards_maps_types_and_project_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/rest/api/2/project":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "10000",
                            "key": "ENG",
                            "name": "Engineering",
                        }
                    ],
                )

            assert request.url.path == "/rest/agile/1.0/board"
            assert request.url.params["projectKeyOrId"] == "10000"
            return httpx.Response(
                200,
                json={
                    "startAt": 0,
                    "maxResults": 50,
                    "isLast": True,
                    "values": [
                        {
                            "id": 31,
                            "name": "Engineering Scrum",
                            "type": "scrum",
                            "location": {"projectId": 10000, "projectKey": "ENG"},
                            "self": "https://jira.example.com/rest/agile/1.0/board/31",
                        },
                        {
                            "id": 32,
                            "name": "Engineering Kanban",
                            "type": "kanban",
                            "location": {"projectId": 10000, "projectKey": "ENG"},
                        },
                        {
                            "id": 33,
                            "name": "Engineering Simple",
                            "type": "simple",
                            "location": {"projectId": 10000, "projectKey": "ENG"},
                        },
                    ],
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
                "auth_email": "jira.email@example.com",
            }
        )

        projects = await connector.list_projects()
        boards = await connector.list_boards("10000")
        await connector.close()

        assert [board.external_id for board in boards] == ["31", "32", "33"]
        assert [board.type for board in boards] == [
            BoardType.SCRUM,
            BoardType.KANBAN,
            BoardType.OTHER,
        ]
        assert all(board.project_id == projects[0].id for board in boards)
        assert (
            boards[0].source_url
            == "https://jira.example.com/jira/software/c/projects/ENG/boards/31"
        )
        assert boards[0].source_metadata == {
            "self": "https://jira.example.com/rest/agile/1.0/board/31",
            "location": {"projectId": 10000, "projectKey": "ENG"},
        }

    asyncio.run(run())


def test_agile_list_calls_preserve_jira_context_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_paths: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path.endswith("/board"):
                return httpx.Response(
                    200,
                    json={"startAt": 0, "maxResults": 50, "isLast": True, "values": []},
                )
            return httpx.Response(
                200,
                json={"startAt": 0, "maxResults": 50, "isLast": True, "values": []},
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com/jira",
                "token": "jira-token-1234",
                "auth_email": "jira.email@example.com",
            }
        )

        await connector.list_boards("10000")
        await connector.list_sprints("31")
        await connector.close()

    asyncio.run(run())

    assert seen_paths == [
        "/jira/rest/agile/1.0/board",
        "/jira/rest/agile/1.0/board/31/sprint",
    ]


def test_list_sprints_maps_states_dates_goal_and_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/rest/agile/1.0/board/31/sprint"
            if request.url.params["startAt"] == "0":
                return httpx.Response(
                    200,
                    json={
                        "startAt": 0,
                        "maxResults": 50,
                        "isLast": False,
                        "values": [
                            {
                                "id": 401,
                                "self": "https://jira.example.com/rest/agile/1.0/sprint/401",
                                "state": "active",
                                "name": "Sprint 24",
                                "startDate": "2026-06-01T09:00:00.000+0200",
                                "endDate": "2026-06-15T17:00:00.000+0200",
                                "goal": "Stabilize reporting",
                                "originBoardId": 31,
                            }
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "startAt": 1,
                    "maxResults": 50,
                    "isLast": True,
                    "values": [
                        {
                            "id": 402,
                            "state": "future",
                            "name": "Sprint 25",
                        },
                        {
                            "id": 403,
                            "state": "closed",
                            "name": "Sprint 23",
                            "completeDate": "2026-05-31T15:00:00.000Z",
                        },
                    ],
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
                "auth_email": "jira.email@example.com",
            }
        )

        sprints = await connector.list_sprints("31")
        await connector.close()

        assert [sprint.external_id for sprint in sprints] == ["401", "402", "403"]
        assert [sprint.state for sprint in sprints] == [
            SprintState.ACTIVE,
            SprintState.FUTURE,
            SprintState.CLOSED,
        ]
        assert sprints[0].name == "Sprint 24"
        assert sprints[0].start_date == datetime(2026, 6, 1, 7, 0, tzinfo=timezone.utc)
        assert sprints[0].end_date == datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
        assert sprints[0].goal == "Stabilize reporting"
        assert sprints[0].source_metadata == {
            "originBoardId": 31,
            "self": "https://jira.example.com/rest/agile/1.0/sprint/401",
        }
        assert sprints[1].start_date is None
        assert sprints[2].complete_date == datetime(2026, 5, 31, 15, 0, tzinfo=timezone.utc)
        assert all(sprint.board_id == sprints[0].board_id for sprint in sprints)

    asyncio.run(run())
