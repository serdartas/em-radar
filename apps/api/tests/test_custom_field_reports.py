# SPDX-License-Identifier: Apache-2.0
"""Tests for custom-field integration in the reports route.

Covers:
- _referenced_custom_field_ids unit tests
- End-to-end report run with a custom-field signal produces findings and
  passes custom_field_ids through WorkItemScope
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from fastapi.testclient import TestClient

from em_radar_core.connectors import WorkItemScope
from em_radar_core.models import (
    EvaluationWindow,
    ReportSettings,
    SignalDefinition,
    SignalOrigin,
    Source,
    StatusCategory,
    Transition,
    WorkItem,
    WorkItemType,
)
from em_radar_connector_jira.connector import JiraConnector

from em_radar_api.routers.reports import _referenced_custom_field_ids

from test_source_connection_routes import (
    FrozenReportDateTime,
    JiraTestConnector,
    _REPORT_STARTED_AT,
    _create_board_scope,
    _create_jira_connection,
    _create_jira_team,
    _run_report,
)


_JIRA_SCHEMA = JiraConnector.describe_signal_schema()
_NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)


def _definition(expression: dict[str, object]) -> SignalDefinition:
    return SignalDefinition(
        name="test",
        entity_type="issue",
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="hygiene"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=_NOW,
        updated_at=_NOW,
    )


# ---------------------------------------------------------------------------
# _referenced_custom_field_ids unit tests
# ---------------------------------------------------------------------------


class TestReferencedCustomFieldIds:
    def test_builtin_field_excluded(self) -> None:
        defn = _definition(
            {
                "type": "group",
                "operator": "all",
                "conditions": [{"field": "status_category", "operator": "is", "value": "done"}],
            }
        )
        result = _referenced_custom_field_ids([defn], _JIRA_SCHEMA)
        assert result == []

    def test_custom_field_included(self) -> None:
        defn = _definition(
            {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "customfield_10100", "operator": "is", "value": "Backend"}
                ],
            }
        )
        result = _referenced_custom_field_ids([defn], _JIRA_SCHEMA)
        assert result == ["customfield_10100"]

    def test_multiple_custom_fields_sorted_and_deduped(self) -> None:
        defn = _definition(
            {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "customfield_10200", "operator": "is_empty"},
                    {"field": "customfield_10100", "operator": "is", "value": "x"},
                    {"field": "customfield_10100", "operator": "is_not", "value": "y"},
                ],
            }
        )
        result = _referenced_custom_field_ids([defn], _JIRA_SCHEMA)
        assert result == ["customfield_10100", "customfield_10200"]

    def test_empty_definitions_returns_empty(self) -> None:
        assert _referenced_custom_field_ids([], _JIRA_SCHEMA) == []

    def test_mixed_builtin_and_custom(self) -> None:
        defn = _definition(
            {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "status_category", "operator": "is", "value": "in_progress"},
                    {"field": "customfield_10100", "operator": "greater_than", "value": 5},
                ],
            }
        )
        result = _referenced_custom_field_ids([defn], _JIRA_SCHEMA)
        assert result == ["customfield_10100"]


# ---------------------------------------------------------------------------
# End-to-end: custom-field signal finds matching work item
# ---------------------------------------------------------------------------


class _JiraCustomFieldConnector(JiraTestConnector):
    """Jira fake that yields one work item with a custom field value and records the scope."""

    received_scopes: ClassVar[list[WorkItemScope]] = []

    @classmethod
    def reset(cls) -> None:
        cls.received_scopes = []

    async def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]:
        _JiraCustomFieldConnector.received_scopes.append(scope)
        # Sprint id must match JiraTestConnector.list_sprints so _workitems_for_scope
        # (board scope type) includes this item during evaluation.
        sprint_id = UUID("45cdfd02-9cde-4c65-a618-7728fc9fb495")
        item = WorkItem(
            id=UUID("80a0d17d-5fb4-46c4-bc3a-e8b4f85c9cb0"),
            source=Source.JIRA,
            external_id="PLAT-1",
            project_id=UUID("4c7a2c4f-e62f-4a78-bf6f-81f0a2a08826"),
            key="PLAT-1",
            type=WorkItemType.TASK,
            title="High priority item",
            status="In Progress",
            status_category=StatusCategory.IN_PROGRESS,
            sprint_ids=[sprint_id],
            current_sprint_id=sprint_id,
            created_at=_REPORT_STARTED_AT,
            updated_at=_REPORT_STARTED_AT,
        )
        item.custom_fields = {"customfield_10100": 90.0}
        yield item

    async def fetch_transitions(
        self,
        entity_type: str,
        entity_external_ids: list[str],
    ) -> AsyncIterator[Transition]:
        return
        yield  # make it an async generator


class _JiraCustomFieldDiscoveryFailureConnector(JiraTestConnector):
    """Jira fake that yields a work item but reports custom-field discovery as unavailable."""

    async def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]:
        # Mirror the real connector: discovery failed, so custom fields are dropped and the
        # degradation is flagged for the router to surface.
        self.custom_fields_unavailable = True
        sprint_id = UUID("45cdfd02-9cde-4c65-a618-7728fc9fb495")
        item = WorkItem(
            id=UUID("80a0d17d-5fb4-46c4-bc3a-e8b4f85c9cb0"),
            source=Source.JIRA,
            external_id="PLAT-1",
            project_id=UUID("4c7a2c4f-e62f-4a78-bf6f-81f0a2a08826"),
            key="PLAT-1",
            type=WorkItemType.TASK,
            title="Item without custom fields",
            status="In Progress",
            status_category=StatusCategory.IN_PROGRESS,
            sprint_ids=[sprint_id],
            current_sprint_id=sprint_id,
            created_at=_REPORT_STARTED_AT,
            updated_at=_REPORT_STARTED_AT,
        )
        yield item

    async def fetch_transitions(
        self,
        entity_type: str,
        entity_external_ids: list[str],
    ) -> AsyncIterator[Transition]:
        return
        yield  # make it an async generator


def test_custom_field_discovery_failure_produces_partial_data_note(
    api_client: TestClient,
    monkeypatch,
) -> None:
    """When custom-field discovery fails, the report succeeds with a custom_fields note."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_JiraCustomFieldDiscoveryFailureConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, ["sprint", "statuses"])

    definition = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "High priority score",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "customfield_10100", "operator": "greater_than", "value": 50}
                ],
            },
            "report_settings": {"severity": "warning", "category": "hygiene"},
            "origin": "user_created",
        },
    ).json()
    assert "id" in definition, f"signal creation failed: {definition}"

    group = api_client.post(
        "/api/signal-config-groups",
        json={"name": "Custom field signals", "signal_ids": [definition["id"]]},
    ).json()

    team_id = _create_jira_team(
        api_client,
        connection_id,
        scope_id,
        "scrum",
        sprint_length_days=14,
        group_ids=[group["id"]],
    )

    report = _run_report(api_client, team_id)
    assert report.get("status") == "succeeded", f"report failed: {report.get('error')}"

    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    assert any(n["source"] == "custom_fields" for n in notes), notes


def test_custom_field_discovery_failure_suppresses_findings(
    api_client: TestClient,
    monkeypatch,
) -> None:
    """When custom-field discovery fails, custom-field signals produce no findings."""
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_JiraCustomFieldDiscoveryFailureConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, ["sprint", "statuses"])

    definition = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Blocked custom field signal",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [{"field": "customfield_10100", "operator": "is_empty"}],
            },
            "report_settings": {"severity": "warning", "category": "hygiene"},
            "origin": "user_created",
        },
    ).json()
    assert "id" in definition, f"signal creation failed: {definition}"

    group = api_client.post(
        "/api/signal-config-groups",
        json={"name": "Custom field signals", "signal_ids": [definition["id"]]},
    ).json()

    team_id = _create_jira_team(
        api_client,
        connection_id,
        scope_id,
        "scrum",
        sprint_length_days=14,
        group_ids=[group["id"]],
    )

    report = _run_report(api_client, team_id)
    assert report.get("status") == "succeeded", f"report failed: {report.get('error')}"

    notes = report["signal_pack_snapshot"]["partial_data_notes"]
    assert any(n["source"] == "custom_fields" for n in notes), notes
    findings = report["findings"]
    assert not any(f["signal_id"] == definition["id"] for f in findings), (
        "custom-field signal should produce no findings when discovery failed"
    )


def test_custom_field_signal_produces_finding_and_scope_receives_field_ids(
    api_client: TestClient,
    monkeypatch,
) -> None:
    """A signal referencing a custom field produces a finding when the work item matches,
    and the connector's WorkItemScope contains the referenced custom field id."""
    _JiraCustomFieldConnector.reset()
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [_JiraCustomFieldConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)

    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, ["sprint", "statuses"])

    definition = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "High priority score",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {"field": "customfield_10100", "operator": "greater_than", "value": 50}
                ],
            },
            "report_settings": {"severity": "warning", "category": "hygiene"},
            "origin": "user_created",
        },
    ).json()
    assert "id" in definition, f"signal creation failed: {definition}"

    group = api_client.post(
        "/api/signal-config-groups",
        json={"name": "Custom field signals", "signal_ids": [definition["id"]]},
    ).json()

    team_id = _create_jira_team(
        api_client,
        connection_id,
        scope_id,
        "scrum",
        sprint_length_days=14,
        group_ids=[group["id"]],
    )

    report = _run_report(api_client, team_id)
    assert report.get("status") != "failed", f"report failed: {report.get('error')}"

    findings = report["findings"]
    assert any(f["signal_id"] == definition["id"] for f in findings), (
        "expected at least one finding from the custom-field signal"
    )

    assert len(_JiraCustomFieldConnector.received_scopes) == 1
    received_scope = _JiraCustomFieldConnector.received_scopes[0]
    assert "customfield_10100" in received_scope.custom_field_ids
