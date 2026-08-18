import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.connectors import ConnectorNotFoundError, ConnectorTransientError, WorkItemScope
from em_radar_core.models import (
    EvaluationWindow,
    StatusCategory,
    WindowType,
    WorkItem,
    WorkItemType,
)


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_fetch_workitems_normalizes_fixture_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_jql: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_jql.append(request.url.params["jql"])
            assert request.url.path == "/rest/api/2/search/jql"
            assert "startAt" not in request.url.params
            assert request.url.params["maxResults"] == "50"
            assert "customfield_10016" in request.url.params["fields"]
            return httpx.Response(
                200,
                json={
                    "issues": [
                        _issue(
                            issue_id="10001",
                            key="ENG-1",
                            issue_type="Epic",
                            status_category="new",
                            status="To Do",
                        ),
                        _issue(
                            issue_id="10002",
                            key="ENG-2",
                            issue_type="Story",
                            status_category="indeterminate",
                            status="In Progress",
                            parent={"id": "10001", "key": "ENG-1"},
                            sprints=[
                                {"id": 401, "state": "closed", "name": "Sprint 23"},
                                {"id": 402, "state": "active", "name": "Sprint 24"},
                            ],
                            labels=["team-a"],
                            components=[{"name": "API"}],
                            story_points=5,
                            assignee={"accountId": "user-1", "displayName": "Ada"},
                            reporter={"accountId": "user-2", "displayName": "Grace"},
                        ),
                        _issue(
                            issue_id="10003",
                            key="ENG-3",
                            issue_type="Bug",
                            status_category="done",
                            status="Done",
                            resolutiondate="2026-06-10T12:00:00.000Z",
                            labels=["blocked"],
                            parent={"id": "10001", "key": "ENG-1"},
                        ),
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

        workitems = await _collect(
            connector.fetch_workitems(
                WorkItemScope(
                    project_external_ids=["10000"],
                    workitem_types=[WorkItemType.EPIC, WorkItemType.STORY, WorkItemType.BUG],
                ),
                _date_window(),
            )
        )
        await connector.close()

        epic, story, bug = workitems
        assert epic.external_id == "10001"
        assert epic.key == "ENG-1"
        assert epic.type is WorkItemType.EPIC
        assert epic.status_category is StatusCategory.TODO
        assert epic.parent_id is None

        assert story.type is WorkItemType.STORY
        assert story.status_category is StatusCategory.IN_PROGRESS
        assert story.parent_id == epic.id
        assert story.current_sprint_id is not None
        assert story.current_sprint_id in story.sprint_ids
        assert len(story.sprint_ids) == 2
        assert story.labels == ["team-a"]
        assert story.components == ["API"]
        assert story.story_points == 5
        assert story.assignee_id is not None
        assert story.reporter_id is not None

        assert bug.type is WorkItemType.BUG
        assert bug.status_category is StatusCategory.BLOCKED
        assert bug.is_blocked is True
        assert bug.resolved_at is None
        assert bug.parent_id == epic.id
        assert all(isinstance(workitem, WorkItem) for workitem in workitems)

    asyncio.run(run())

    assert seen_jql == [
        'project in ("10000") AND issuetype in ("Epic", "Story", "Bug") '
        'AND updated < "2026-06-15 00:00"'
    ]


def test_fetch_workitems_filters_sprint_windows_to_selected_sprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_sprint_id = jira_connector_module._stable_id("sprint", "402")
    seen_jql: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_jql.append(request.url.params["jql"])
            return httpx.Response(
                200,
                json={
                    "issues": [
                        _issue(
                            issue_id="10001",
                            key="ENG-1",
                            sprints=[{"id": 401, "state": "active", "name": "Sprint 23"}],
                        ),
                        _issue(
                            issue_id="10002",
                            key="ENG-2",
                            sprints=[{"id": 402, "state": "active", "name": "Sprint 24"}],
                        ),
                        _issue(issue_id="10003", key="ENG-3"),
                    ],
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        workitems = await _collect(
            connector.fetch_workitems(
                WorkItemScope(project_external_ids=["10000"]),
                _sprint_window(selected_sprint_id),
            )
        )
        await connector.close()

        assert [workitem.key for workitem in workitems] == ["ENG-2"]
        assert workitems[0].current_sprint_id == selected_sprint_id

    asyncio.run(run())

    assert seen_jql == ['project in ("10000")']


@pytest.mark.parametrize(
    ("case", "expected_count", "expected_tokens"),
    [
        ("empty", 0, [None]),
        ("partial", 1, [None]),
        ("full", 52, [None, "page-2"]),
    ],
)
def test_fetch_workitems_handles_empty_partial_and_full_pages(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_count: int,
    expected_tokens: list[str | None],
) -> None:
    seen_tokens: list[str | None] = []

    async def run() -> None:
        pages = _pages_for_case(case)

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/rest/api/2/search/jql"
            seen_tokens.append(request.url.params.get("nextPageToken"))
            page_index = len(seen_tokens) - 1
            body: dict[str, object] = {"issues": pages[page_index]}
            if page_index < len(pages) - 1:
                body["nextPageToken"] = f"page-{page_index + 2}"
            return httpx.Response(200, json=body)

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        workitems = await _collect(
            connector.fetch_workitems(WorkItemScope(project_external_ids=["10000"]), _date_window())
        )
        await connector.close()

        assert len(workitems) == expected_count
        assert all(workitem.current_sprint_id is None for workitem in workitems)

    asyncio.run(run())

    assert seen_tokens == expected_tokens


def _pages_for_case(case: str) -> list[list[Mapping[str, object]]]:
    if case == "empty":
        return [[]]
    if case == "partial":
        return [[_issue(issue_id="10001", key="ENG-1")]]
    if case == "full":
        return [
            [_issue(issue_id=str(10000 + index), key=f"ENG-{index}") for index in range(1, 51)],
            [_issue(issue_id="10051", key="ENG-51"), _issue(issue_id="10052", key="ENG-52")],
        ]
    raise AssertionError(f"unknown case: {case}")


def test_fetch_workitems_falls_back_to_classic_search_when_jql_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_paths: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path == "/rest/api/2/search/jql":
                return httpx.Response(404)
            assert request.url.path == "/rest/api/2/search"
            assert request.url.params["startAt"] == "0"
            return httpx.Response(
                200,
                json={
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                    "issues": [_issue(issue_id="10001", key="ENG-1")],
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        workitems = await _collect(
            connector.fetch_workitems(WorkItemScope(project_external_ids=["10000"]), _date_window())
        )
        await connector.close()

        assert [workitem.key for workitem in workitems] == ["ENG-1"]

    asyncio.run(run())

    assert seen_paths == ["/rest/api/2/search/jql", "/rest/api/2/search"]


def test_fetch_workitems_date_range_jql_uses_exclusive_upper_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DATE_RANGE windows must emit updated < end in the JQL (exclusive end, half-open [start, end)).

    No lower bound is added — stale in-progress issues (e.g. updated 20+ days ago)
    must not be excluded because signals like StaleInProgressSignal target them
    intentionally.
    """
    seen_jql: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_jql.append(request.url.params["jql"])
            return httpx.Response(200, json={"issues": []})

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        await _collect(
            connector.fetch_workitems(
                WorkItemScope(project_external_ids=["10000"]),
                _date_window(),
            )
        )
        await connector.close()

    asyncio.run(run())

    assert len(seen_jql) == 1
    assert "updated >= " not in seen_jql[0]
    assert 'updated < "2026-06-15 00:00"' in seen_jql[0]
    assert 'updated <= "2026-06-15 00:00"' not in seen_jql[0]


def test_fetch_workitems_non_midnight_end_ceil_and_exact_postfilter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DATE_RANGE with a non-minute-aligned end must ceil the JQL boundary and apply
    an exact exclusive-end post-filter so the final partial minute is handled correctly.

    window.end = 2026-06-15T14:30:45Z
      - JQL must use updated < "2026-06-15 14:31"  (ceiled, NOT 14:30)
      - issue updated at 14:30:10 IS returned (inside the window)
      - issue updated at 14:30:45 is EXCLUDED (exactly at end — exclusive)
      - issue updated at 14:30:50 is EXCLUDED (after the exact end, same minute)
    """
    seen_jql: list[str] = []

    async def run() -> None:
        # All three issues are returned by the mock API (the JQL is coarse).
        # The exact post-filter under test must exclude the last two.
        def handler(request: httpx.Request) -> httpx.Response:
            seen_jql.append(request.url.params["jql"])
            return httpx.Response(
                200,
                json={
                    "issues": [
                        _issue(
                            issue_id="10001",
                            key="ENG-1",
                            updated="2026-06-15T14:30:10.000Z",  # inside — kept
                        ),
                        _issue(
                            issue_id="10002",
                            key="ENG-2",
                            updated="2026-06-15T14:30:45.000Z",  # at end — excluded
                        ),
                        _issue(
                            issue_id="10003",
                            key="ENG-3",
                            updated="2026-06-15T14:30:50.000Z",  # after end — excluded
                        ),
                    ]
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            end=datetime(2026, 6, 15, 14, 30, 45, tzinfo=timezone.utc),
            team_profile_id=uuid4(),
        )
        workitems = await _collect(
            connector.fetch_workitems(WorkItemScope(project_external_ids=["10000"]), window)
        )
        await connector.close()

        assert len(workitems) == 1
        assert workitems[0].key == "ENG-1"

    asyncio.run(run())

    assert len(seen_jql) == 1
    # Ceiled boundary: 14:30:45 → 14:31
    assert 'updated < "2026-06-15 14:31"' in seen_jql[0], f"unexpected JQL: {seen_jql[0]}"
    # Must NOT use the truncated (floor) boundary
    assert 'updated < "2026-06-15 14:30"' not in seen_jql[0]


def test_fetch_workitems_mid_stream_404_raises_without_restarting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 on page 2+ must propagate as ConnectorNotFoundError.

    It must not silently fall back to the legacy startAt=0 endpoint, which would
    re-yield already-emitted page-1 issues as duplicates.
    """
    seen_paths: list[str] = []
    yielded_before_error: list[WorkItem] = []

    async def run() -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            seen_paths.append(request.url.path)
            if call_count == 1:
                return httpx.Response(
                    200,
                    json={
                        "issues": [_issue(issue_id="10001", key="ENG-1")],
                        "nextPageToken": "page-2",
                    },
                )
            return httpx.Response(404)

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )

        with pytest.raises(ConnectorNotFoundError):
            async for item in connector.fetch_workitems(
                WorkItemScope(project_external_ids=["10000"]),
                _date_window(),
            ):
                yielded_before_error.append(item)

        await connector.close()

    asyncio.run(run())

    assert seen_paths == ["/rest/api/2/search/jql", "/rest/api/2/search/jql"]
    assert "/rest/api/2/search" not in seen_paths
    assert [item.key for item in yielded_before_error] == ["ENG-1"]


def test_fetch_workitems_epic_with_native_parent_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Jira Epic with a native parent (Initiative) must produce a valid WorkItem without raising.

    Before this fix the model validator forbade any parent_id on EPICs, so this caused a 500
    crash when the report runner ingested an Epic sitting under an Initiative.
    """

    async def run() -> list[WorkItem]:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "issues": [
                        _issue(
                            issue_id="10000",
                            key="ENG-0",
                            issue_type="Initiative",
                            status_category="new",
                            status="To Do",
                        ),
                        _issue(
                            issue_id="10001",
                            key="ENG-1",
                            issue_type="Epic",
                            status_category="new",
                            status="To Do",
                            parent={"id": "10000", "key": "ENG-0"},
                        ),
                    ]
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
            }
        )
        workitems = await _collect(
            connector.fetch_workitems(
                WorkItemScope(
                    project_external_ids=["10000"],
                    workitem_types=[WorkItemType.EPIC],
                ),
                _date_window(),
            )
        )
        await connector.close()
        return workitems

    workitems = asyncio.run(run())

    assert len(workitems) == 2
    initiative, epic = workitems
    assert initiative.type is WorkItemType.OTHER
    assert epic.type is WorkItemType.EPIC
    assert epic.parent_id == initiative.id


def test_fetch_workitems_wraps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
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

        with pytest.raises(ConnectorTransientError):
            await _collect(
                connector.fetch_workitems(
                    WorkItemScope(project_external_ids=["10000"]),
                    _date_window(),
                )
            )

        await connector.close()

    asyncio.run(run())


async def _collect(iterator: object) -> list[WorkItem]:
    workitems: list[WorkItem] = []
    async for workitem in iterator:
        workitems.append(workitem)
    return workitems


def _date_window() -> EvaluationWindow:
    return EvaluationWindow(
        window_type=WindowType.DATE_RANGE,
        start=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end=datetime(2026, 6, 15, tzinfo=timezone.utc),
        team_profile_id=uuid4(),
    )


def _sprint_window(sprint_id: UUID) -> EvaluationWindow:
    return EvaluationWindow(
        window_type=WindowType.SPRINT,
        sprint_id=sprint_id,
        team_profile_id=uuid4(),
    )


def _issue(
    *,
    issue_id: str,
    key: str,
    issue_type: str = "Task",
    status_category: str = "new",
    status: str = "To Do",
    parent: Mapping[str, object] | None = None,
    sprints: list[Mapping[str, object]] | None = None,
    labels: list[str] | None = None,
    components: list[Mapping[str, object]] | None = None,
    story_points: int | None = None,
    assignee: Mapping[str, object] | None = None,
    reporter: Mapping[str, object] | None = None,
    resolutiondate: str | None = None,
    epic_link: str | None = None,
    updated: str = "2026-06-02T09:00:00.000+0200",
) -> Mapping[str, object]:
    fields: dict[str, object] = {
        "summary": f"Summary {key}",
        "description": f"Description {key}",
        "issuetype": {"name": issue_type},
        "status": {
            "name": status,
            "statusCategory": {"key": status_category},
        },
        "project": {"id": "10000", "key": "ENG"},
        "labels": labels or [],
        "components": components or [],
        "created": "2026-06-01T09:00:00.000+0200",
        "updated": updated,
        "resolutiondate": resolutiondate,
        "duedate": None,
        "customfield_10016": story_points,
        "customfield_10020": sprints or [],
    }
    if parent is not None:
        fields["parent"] = parent
    if epic_link is not None:
        fields["customfield_10014"] = epic_link
    if assignee is not None:
        fields["assignee"] = assignee
    if reporter is not None:
        fields["reporter"] = reporter

    return {
        "id": issue_id,
        "key": key,
        "self": f"https://jira.example.com/rest/api/2/issue/{issue_id}",
        "fields": fields,
    }
