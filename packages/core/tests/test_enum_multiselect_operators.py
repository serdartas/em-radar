"""Tests for enum multi-select operators: is_any_of, is_none_of, contains_any (AUDIT-23)."""

from uuid import uuid4

from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin
from em_radar_core.signals import SignalData

from _signal_helpers import NOW, context, project, workitem

_SCHEMA = JiraConnector.describe_signal_schema()


def _scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Platform",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "PLAT"},
        capabilities=("statuses", "labels"),
    )


def _definition(expression: dict[str, object]) -> SignalDefinition:
    return SignalDefinition(
        name="Multi-select operator test",
        entity_type="issue",
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="hygiene"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _data(item: object) -> SignalData:
    return SignalData(
        report_id=uuid4(),
        projects=(project(),),
        workitems=(item,),  # type: ignore[arg-type]
    )


class TestIsAnyOf:
    def test_fires_when_observed_value_is_in_list(self) -> None:
        item = workitem(status="In Progress")
        expr: dict[str, object] = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status", "operator": "is_any_of", "value": ["In Progress", "Review"]}
            ],
        }
        findings = evaluate_signal_definition(
            _definition(expr), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1

    def test_does_not_fire_when_observed_value_not_in_list(self) -> None:
        item = workitem(status="In Progress")
        expr: dict[str, object] = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status", "operator": "is_any_of", "value": ["Done", "Review"]}
            ],
        }
        findings = evaluate_signal_definition(
            _definition(expr), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 0


class TestIsNoneOf:
    def test_fires_when_observed_value_not_in_exclusion_list(self) -> None:
        item = workitem(status="In Progress")
        expr: dict[str, object] = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status", "operator": "is_none_of", "value": ["Done", "Review"]}
            ],
        }
        findings = evaluate_signal_definition(
            _definition(expr), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1

    def test_does_not_fire_when_observed_value_in_exclusion_list(self) -> None:
        item = workitem(status="In Progress")
        expr: dict[str, object] = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status", "operator": "is_none_of", "value": ["In Progress", "Review"]}
            ],
        }
        findings = evaluate_signal_definition(
            _definition(expr), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 0


class TestContainsAny:
    def test_fires_when_sets_intersect(self) -> None:
        item = workitem(labels=["backend", "urgent"])
        expr: dict[str, object] = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "labels", "operator": "contains_any", "value": ["backend", "critical"]}
            ],
        }
        findings = evaluate_signal_definition(
            _definition(expr), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1

    def test_does_not_fire_when_intersection_is_empty(self) -> None:
        item = workitem(labels=["backend", "urgent"])
        expr: dict[str, object] = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "labels", "operator": "contains_any", "value": ["frontend", "critical"]}
            ],
        }
        findings = evaluate_signal_definition(
            _definition(expr), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 0
