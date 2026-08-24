# SPDX-License-Identifier: Apache-2.0
"""Regression tests for Jira connector audit fixes."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

import em_radar_connector_jira.connector as jira_connector_module
from em_radar_connector_jira.connector import JiraConnector, _workitem_jql
from em_radar_core.connectors import ConnectorConfigError, ConnectorDataError, WorkItemScope
from em_radar_core.models import EvaluationWindow, WindowType

_DISCOVERY = [
    {
        "id": "customfield_10100",
        "name": "Priority Score",
        "custom": True,
        "schema": {"type": "number"},
    },
    {"id": "summary", "name": "Summary", "custom": False, "schema": {"type": "string"}},
]


def _client_factory_for(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


def _issue() -> dict[str, object]:
    return {
        "id": "10001",
        "key": "PLAT-1",
        "self": "https://jira.example.com/rest/api/2/issue/10001",
        "fields": {
            "summary": "PLAT-1 summary",
            "description": None,
            "issuetype": {"name": "Story"},
            "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
            "project": {"id": "10000", "key": "PLAT"},
            "labels": [],
            "components": [],
            "customfield_10016": None,
            "customfield_10020": [],
            "created": "2026-01-01T09:00:00.000+0000",
            "updated": "2026-01-10T09:00:00.000+0000",
            "resolutiondate": None,
            "duedate": None,
        },
    }


class TestUndiscoveredCustomFieldsNotRequested:
    def test_only_discovered_ids_are_sent_in_jql_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        jira_connector_module._field_discovery_cache.clear()  # type: ignore[attr-defined]
        captured_fields: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/field"):
                return httpx.Response(200, json=_DISCOVERY)
            captured_fields.append(request.url.params.get("fields", ""))
            return httpx.Response(200, json={"issues": [_issue()]})

        monkeypatch.setattr(jira_connector_module, "CLIENT_FACTORY", _client_factory_for(handler))
        connector = JiraConnector(
            config={"base_url": "https://jira.example.com", "token": "demo-token-123456789012"}
        )
        scope = WorkItemScope(
            project_external_ids=["10000"],
            board_external_ids=["20000"],
            # customfield_99999 is requested but discovery does not return it.
            custom_field_ids=["customfield_10100", "customfield_99999"],
        )
        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=datetime(2026, 6, 1, tzinfo=UTC),
            end=datetime(2026, 6, 17, tzinfo=UTC),
            team_profile_id=uuid4(),
        )

        async def run() -> None:
            async for _ in connector.fetch_workitems(scope, window):
                pass

        asyncio.run(run())
        assert captured_fields, "search endpoint was never called"
        fields = captured_fields[0]
        assert "customfield_10100" in fields
        assert "customfield_99999" not in fields


class TestSprintJqlGuards:
    def _window(self) -> EvaluationWindow:
        return EvaluationWindow(
            window_type=WindowType.SPRINT, sprint_id=uuid4(), team_profile_id=uuid4()
        )

    def test_unbounded_sprint_window_is_rejected(self) -> None:
        scope = WorkItemScope(project_external_ids=[], board_external_ids=[])
        with pytest.raises(ConnectorDataError, match="sprint or project scope"):
            _workitem_jql(scope, self._window())

    def test_non_numeric_sprint_id_is_rejected(self) -> None:
        scope = WorkItemScope(
            project_external_ids=[], board_external_ids=[], sprint_external_id="abc; DROP"
        )
        with pytest.raises(ConnectorDataError, match="numeric"):
            _workitem_jql(scope, self._window())

    def test_numeric_sprint_id_builds_clause(self) -> None:
        scope = WorkItemScope(
            project_external_ids=[], board_external_ids=[], sprint_external_id="123"
        )
        assert "sprint = 123" in _workitem_jql(scope, self._window())

    def test_project_scoped_sprint_without_sprint_id_is_allowed(self) -> None:
        scope = WorkItemScope(project_external_ids=["10000"], board_external_ids=[])
        jql = _workitem_jql(scope, self._window())
        assert "project in" in jql


class TestConfigErrorDoesNotLeakOrChain:
    def test_invalid_config_is_not_chained_and_hides_value(self) -> None:
        with pytest.raises(ConnectorConfigError) as exc_info:
            JiraConnector(config={"base_url": "https://jira.example.com", "token": 12345})
        # Chain is broken so the pydantic error (which can carry the raw input) is not attached.
        assert exc_info.value.__cause__ is None
        message = str(exc_info.value)
        assert "12345" not in message
        assert "token" in message
