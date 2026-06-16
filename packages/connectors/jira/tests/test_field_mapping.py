import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.connectors import WorkItemScope
from em_radar_core.models import EvaluationWindow, StatusCategory, WindowType, WorkItem


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def test_fetch_workitems_applies_field_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_fields: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_fields.append(request.url.params["fields"])
            return httpx.Response(
                200,
                json={
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                    "issues": [_issue()],
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
                "field_mapping": {
                    "story_points": "customfield_20000",
                    "blocked_label": "impediment",
                },
            }
        )

        workitems = await _collect(
            connector.fetch_workitems(WorkItemScope(project_external_ids=["10000"]), _date_window())
        )
        await connector.close()

        assert len(workitems) == 1
        workitem = workitems[0]
        assert workitem.story_points == 8
        assert workitem.acceptance_criteria == "- API returns 200\n- Audit event is recorded"
        assert workitem.status_category is StatusCategory.BLOCKED
        assert workitem.is_blocked is True

    asyncio.run(run())

    assert seen_fields == [
        "summary,description,issuetype,status,assignee,reporter,project,parent,labels,"
        "components,created,updated,resolutiondate,duedate,customfield_10020,"
        "customfield_20000,customfield_10014"
    ]


def test_fetch_workitems_reads_acceptance_criteria_custom_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_fields: list[str] = []

    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen_fields.append(request.url.params["fields"])
            return httpx.Response(
                200,
                json={
                    "startAt": 0,
                    "maxResults": 50,
                    "total": 1,
                    "issues": [_issue(acceptance_criteria="Custom acceptance criteria")],
                },
            )

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            {
                "base_url": "https://jira.example.com",
                "token": "jira-token-1234",
                "field_mapping": {
                    "acceptance_criteria": "customfield_30000",
                },
            }
        )

        workitems = await _collect(
            connector.fetch_workitems(WorkItemScope(project_external_ids=["10000"]), _date_window())
        )
        await connector.close()

        assert workitems[0].acceptance_criteria == "Custom acceptance criteria"

    asyncio.run(run())

    assert seen_fields == [
        "summary,description,issuetype,status,assignee,reporter,project,parent,labels,"
        "components,created,updated,resolutiondate,duedate,customfield_10020,"
        "customfield_10016,customfield_10014,customfield_30000"
    ]


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


def _issue(*, acceptance_criteria: str | None = None) -> Mapping[str, object]:
    fields: dict[str, object] = {
        "summary": "Summary ENG-1",
        "description": (
            "Story details\n\n"
            "### Acceptance Criteria\n"
            "- API returns 200\n"
            "- Audit event is recorded\n\n"
            "### Notes\n"
            "Follow-up later"
        ),
        "issuetype": {"name": "Story"},
        "status": {
            "name": "In Progress",
            "statusCategory": {"key": "indeterminate"},
        },
        "project": {"id": "10000", "key": "ENG"},
        "labels": ["team-a", "impediment"],
        "components": [],
        "created": "2026-06-01T09:00:00.000+0200",
        "updated": "2026-06-02T09:00:00.000+0200",
        "resolutiondate": None,
        "duedate": None,
        "customfield_10020": [],
        "customfield_20000": 8,
    }
    if acceptance_criteria is not None:
        fields["customfield_30000"] = acceptance_criteria

    return {
        "id": "10001",
        "key": "ENG-1",
        "self": "https://jira.example.com/rest/api/2/issue/10001",
        "fields": fields,
    }
