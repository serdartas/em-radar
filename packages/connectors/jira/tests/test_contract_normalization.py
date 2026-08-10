import asyncio
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import JiraConnector, JiraFieldMappingConfig
from em_radar_core.connectors import (
    ConnectorAuthError,
    ConnectorConfigError,
    ConnectorDataError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitedError,
    ConnectorTransientError,
    TransitionProvider,
    WorkItemProvider,
)
from em_radar_core.models import (
    BoardType,
    EntityType,
    Source,
    SprintState,
    StatusCategory,
    Transition,
    WorkItem,
    WorkItemType,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_describe_capabilities_matches_implemented_methods() -> None:
    connector = JiraConnector(
        {
            "base_url": "https://jira.example.com",
            "token": "jira-token-1234",
        }
    )
    capabilities = JiraConnector.describe_capabilities()

    assert capabilities.provides_workitems is True
    assert isinstance(connector, WorkItemProvider)
    assert callable(connector.list_projects)
    assert callable(connector.list_boards)
    assert callable(connector.list_sprints)
    assert callable(connector.fetch_workitems)

    assert capabilities.provides_sprints is True
    assert callable(connector.list_sprints)

    assert capabilities.provides_transitions is True
    assert isinstance(connector, TransitionProvider)
    assert callable(connector.fetch_transitions)

    assert capabilities.provides_mergerequests is False
    assert not hasattr(connector, "list_repositories")
    assert not hasattr(connector, "fetch_mergerequests")
    assert capabilities.provides_repositories is False
    assert capabilities.provides_reviews is False
    assert capabilities.provides_comments is False
    assert capabilities.supports_incremental_fetch is True
    assert capabilities.supports_pagination_cursor is False
    assert capabilities.max_window_days is None

    asyncio.run(connector.close())


def test_static_issue_fixture_normalizes_to_canonical_workitems() -> None:
    payload = _load_fixture("issues_page.json")
    workitems = [
        jira_connector_module._workitem_from_payload(
            issue,
            "https://jira.example.com",
            JiraFieldMappingConfig(),
        )
        for issue in jira_connector_module._payload_issues(payload)
    ]

    epic, story, bug = workitems

    assert [workitem.key for workitem in workitems] == ["ENG-1", "ENG-2", "ENG-3"]
    assert all(workitem.source is Source.JIRA for workitem in workitems)
    assert all(
        workitem.source_url == f"https://jira.example.com/browse/{workitem.key}"
        for workitem in workitems
    )
    assert len({workitem.id for workitem in workitems}) == len(workitems)

    assert epic.type is WorkItemType.EPIC
    assert epic.parent_id is None
    assert epic.status_category is StatusCategory.TODO

    assert story.type is WorkItemType.STORY
    assert story.parent_id == epic.id
    assert story.status_category is StatusCategory.IN_PROGRESS
    assert story.assignee_id == jira_connector_module._stable_id("user", "user-1")
    assert story.reporter_id == jira_connector_module._stable_id("user", "user-2")
    assert story.labels == ["team-a"]
    assert story.components == ["Connectors"]
    assert story.story_points == 5.0
    assert story.acceptance_criteria == "- Issues are normalized\n- Pagination is covered"
    assert story.current_sprint_id == jira_connector_module._stable_id("sprint", "402")

    assert bug.type is WorkItemType.BUG
    assert bug.parent_id == epic.id
    assert bug.status_category is StatusCategory.DONE
    assert bug.resolved_at is not None
    assert bug.components == ["Reports"]

    for workitem in workitems:
        _assert_workitem_invariants(workitem)


def test_static_board_and_sprint_fixtures_normalize() -> None:
    boards_payload = _load_fixture("boards_page.json")
    sprints_payload = _load_fixture("sprints_page.json")

    boards = [
        jira_connector_module._board_from_payload(payload, "https://jira.example.com", "10000")
        for payload in jira_connector_module._payload_values(boards_payload)
    ]
    sprints = [
        jira_connector_module._sprint_from_payload(payload, "31")
        for payload in jira_connector_module._payload_values(sprints_payload)
    ]

    assert [board.external_id for board in boards] == ["31", "32"]
    assert [board.type for board in boards] == [BoardType.SCRUM, BoardType.KANBAN]
    assert boards[0].project_id == jira_connector_module._stable_id("project", "10000")
    assert boards[0].source_metadata == {
        "self": "https://jira.example.com/rest/agile/1.0/board/31",
        "location": {"projectId": 10000, "projectKey": "ENG"},
    }

    assert [sprint.external_id for sprint in sprints] == ["401", "402"]
    assert [sprint.state for sprint in sprints] == [SprintState.CLOSED, SprintState.ACTIVE]
    assert sprints[0].board_id == jira_connector_module._stable_id("board", "31")
    assert sprints[0].complete_date is not None
    assert sprints[1].complete_date is None
    assert all(sprint.source is Source.JIRA for sprint in sprints)


def test_static_changelog_fixture_normalizes_status_transitions() -> None:
    payload = _load_fixture("changelog_page.json")
    status_categories = {
        "1": StatusCategory.TODO,
        "to do": StatusCategory.TODO,
        "2": StatusCategory.IN_PROGRESS,
        "in progress": StatusCategory.IN_PROGRESS,
        "3": StatusCategory.DONE,
        "done": StatusCategory.DONE,
    }

    transitions = jira_connector_module._transitions_from_changelog(
        "ENG-2",
        jira_connector_module._payload_histories(payload),
        status_categories,
    )

    assert [transition.to_status for transition in transitions] == [
        "To Do",
        "In Progress",
        "Done",
    ]
    assert [transition.to_status_category for transition in transitions] == [
        StatusCategory.TODO,
        StatusCategory.IN_PROGRESS,
        StatusCategory.DONE,
    ]
    assert [transition.from_status_category for transition in transitions] == [
        None,
        StatusCategory.TODO,
        StatusCategory.IN_PROGRESS,
    ]
    assert all(transition.entity_type is EntityType.WORKITEM for transition in transitions)
    assert all(
        transition.entity_id == jira_connector_module._stable_id("workitem", "ENG-2")
        for transition in transitions
    )
    assert all(isinstance(transition, Transition) for transition in transitions)
    assert transitions == sorted(transitions, key=lambda transition: transition.occurred_at)


@pytest.mark.parametrize(
    ("page_ids", "expected_count", "expected_starts"),
    [
        ([[]], 0, ["0"]),
        ([[31]], 1, ["0"]),
        (
            [
                list(range(1, 51)),
                [51, 52],
            ],
            52,
            ["0", "50"],
        ),
    ],
)
def test_offset_pagination_handles_empty_partial_and_full_pages(
    monkeypatch: pytest.MonkeyPatch,
    page_ids: list[list[int]],
    expected_count: int,
    expected_starts: list[str],
) -> None:
    seen_starts: list[str] = []
    pages = [[_board_payload(board_id) for board_id in ids] for ids in page_ids]

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/rest/agile/1.0/board"
            start_at = request.url.params["startAt"]
            seen_starts.append(start_at)
            page_index = len(seen_starts) - 1
            return httpx.Response(
                200,
                json={
                    "startAt": int(start_at),
                    "maxResults": 50,
                    "total": sum(len(page) for page in pages),
                    "values": pages[page_index],
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        boards = await connector.list_boards("10000")
        await connector.close()

        assert len(boards) == expected_count

    asyncio.run(run())

    assert seen_starts == expected_starts


def test_pagination_without_progress_raises_typed_data_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/rest/agile/1.0/board"
            return httpx.Response(
                200,
                json={
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                    "values": [],
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        with pytest.raises(ConnectorDataError):
            await connector.list_boards("10000")

        await connector.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (400, ConnectorDataError),
        (401, ConnectorAuthError),
        (403, ConnectorAuthError),
        (404, ConnectorNotFoundError),
        (429, ConnectorRateLimitedError),
        (500, ConnectorTransientError),
    ],
)
def test_http_status_errors_use_typed_connector_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_error: type[ConnectorError],
) -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code)

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        with pytest.raises(expected_error):
            await connector.list_projects()

        await connector.close()

    asyncio.run(run())


def test_request_errors_are_wrapped_and_do_not_escape_as_httpx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down", request=request)

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        with pytest.raises(ConnectorTransientError) as error:
            await connector.list_projects()

        assert not isinstance(error.value, httpx.HTTPError)
        await connector.close()

    asyncio.run(run())


def test_bad_config_raises_typed_config_error() -> None:
    with pytest.raises(ConnectorConfigError):
        JiraConnector(
            {
                "base_url": "not-a-url",
                "token": "jira-token-1234",
            }
        )


def test_optional_real_jira_integration_is_env_gated() -> None:
    if os.environ.get("EM_RADAR_JIRA_INTEGRATION") != "1":
        pytest.skip("Set EM_RADAR_JIRA_INTEGRATION=1 to run against real Jira credentials")

    base_url = os.environ["EM_RADAR_JIRA_BASE_URL"]
    token = os.environ["EM_RADAR_JIRA_TOKEN"]
    auth_email = os.environ.get("EM_RADAR_JIRA_AUTH_EMAIL")

    async def run() -> None:
        config: dict[str, object] = {
            "base_url": base_url,
            "token": token,
        }
        if auth_email is not None:
            config["auth_email"] = auth_email

        connector = JiraConnector(config)
        result = await connector.test_connection()
        await connector.close()

        assert result.ok is True

    asyncio.run(run())


def test_no_category_status_category_helper_returns_todo() -> None:
    status_no_category = {
        "name": "Backlog",
        "statusCategory": {"key": "undefined", "id": 1, "name": "No Category"},
    }
    result = jira_connector_module._status_category(status_no_category, [])
    assert result is StatusCategory.TODO

    status_id_only = {
        "name": "Backlog",
        "statusCategory": {"id": 1, "name": "No Category"},
    }
    result_id_only = jira_connector_module._status_category(status_id_only, [])
    assert result_id_only is StatusCategory.TODO


def test_no_category_issue_normalizes_to_todo_and_is_not_dropped_from_page() -> None:
    issue_payload = {
        "id": "99001",
        "key": "ENG-99",
        "self": "https://jira.example.com/rest/api/2/issue/99001",
        "fields": {
            "summary": "Issue with no status category",
            "issuetype": {"name": "Task"},
            "status": {
                "name": "Backlog",
                "statusCategory": {"key": "undefined", "id": 1, "name": "No Category"},
            },
            "project": {"id": "10000", "key": "ENG"},
            "labels": [],
            "components": [],
        },
    }
    workitem = jira_connector_module._workitem_from_payload(
        issue_payload,
        "https://jira.example.com",
        JiraFieldMappingConfig(),
    )
    assert workitem.status_category is StatusCategory.TODO
    assert workitem.key == "ENG-99"


def test_malformed_status_category_field_still_raises_data_error() -> None:
    status_missing = {"name": "Some Status"}
    with pytest.raises(ConnectorDataError):
        jira_connector_module._status_category(status_missing, [])

    status_non_mapping = {"name": "Some Status", "statusCategory": "not-a-mapping"}
    with pytest.raises(ConnectorDataError):
        jira_connector_module._status_category(status_non_mapping, [])


def _assert_workitem_invariants(workitem: WorkItem) -> None:
    assert workitem.parent_id != workitem.id
    if workitem.type is WorkItemType.EPIC:
        assert workitem.parent_id is None
    if workitem.current_sprint_id is not None:
        assert workitem.current_sprint_id in workitem.sprint_ids
    assert (workitem.status_category is StatusCategory.DONE) == (workitem.resolved_at is not None)


def _load_fixture(name: str) -> Mapping[str, object]:
    payload = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise AssertionError(f"{name} must contain a JSON object")
    return cast(Mapping[str, object], payload)


def _board_payload(board_id: int) -> Mapping[str, object]:
    return {
        "id": board_id,
        "name": f"Board {board_id}",
        "type": "scrum",
        "location": {"projectId": 10000, "projectKey": "ENG"},
    }
