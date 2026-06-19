from datetime import timedelta
from uuid import uuid4

from em_radar_core.evaluation import (
    ExpressionValidationError,
    ScopeDescriptor,
    evaluate_signal_definition,
    validate_expression,
)
from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin, SignalTargetScope
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, board, context, project, sprint, workitem


def _definition(expression: dict[str, object]) -> SignalDefinition:
    return SignalDefinition(
        name="Scoped stale work",
        entity_type="issue",
        target_scopes=[
            SignalTargetScope(connector_id="jira-1", scope_id="scope-1", scope_type="project")
        ],
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _scope(capabilities: tuple[str, ...] = ("statuses", "labels")) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Radar",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "RAD", "name": "Radar"},
        capabilities=capabilities,
    )


def test_all_any_and_nested_groups_produce_reasons() -> None:
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "status_category", "operator": "is", "value": "in_progress"},
            {
                "type": "group",
                "operator": "any",
                "conditions": [
                    {"field": "labels", "operator": "contains", "value": "customer-impact"},
                    {"field": "issue_type", "operator": "is", "value": "bug"},
                ],
            },
        ],
    }
    item = workitem()
    item.labels = ["customer-impact"]

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert "status_category" in findings[0].reason
    assert findings[0].evidence["labels"] == ["customer-impact"]


def test_date_duration_and_deterministic_now_behavior() -> None:
    item = workitem(created_at=NOW - timedelta(days=5), updated_at=NOW - timedelta(days=4))
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {
                "field": "age_since_created",
                "operator": "greater_than",
                "value": {"amount": 3, "unit": "days"},
            },
            {
                "field": "updated_at",
                "operator": "before",
                "value": (NOW - timedelta(days=2)).isoformat(),
            },
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].evidence["age_since_created"] == 5


def test_sprint_field_availability_is_validated() -> None:
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "sprint_day", "operator": "is_after", "value": 1}],
    }

    try:
        validate_expression(expression, JiraConnector.describe_signal_schema(), [_scope()])
    except ExpressionValidationError as error:
        assert "requires scope capability" in str(error)
    else:
        raise AssertionError("sprint field should reject non-sprint scope")


def test_target_scope_filtering_uses_selected_scope_only() -> None:
    selected = workitem(key="RAD-1")
    sibling = workitem(key="OTHER-1")
    sibling.project_id = uuid4()
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "status_category", "operator": "is", "value": "in_progress"}],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(
            report_id=uuid4(),
            projects=(project(),),
            workitems=(selected, sibling),
        ),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [finding.title for finding in findings] == ["RAD-1 - RAD-1 title"]


def test_sprint_relative_fields_match_sprint_scope() -> None:
    current_sprint = sprint(start_date=NOW - timedelta(days=2))
    item = workitem(sprint_ids=[current_sprint.id], current_sprint_id=current_sprint.id)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "sprint_day", "operator": "is_after", "value": 1}],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(
            report_id=uuid4(),
            projects=(project(),),
            boards=(board(),),
            sprints=(current_sprint,),
            workitems=(item,),
        ),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope(("sprint", "statuses", "labels"))],
    )

    assert len(findings) == 1
    assert findings[0].evidence["sprint_day"] == 3
