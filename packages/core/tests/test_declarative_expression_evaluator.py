from datetime import datetime, timedelta, timezone
from uuid import uuid4

from em_radar_core.evaluation import (
    ExpressionValidationError,
    ScopeDescriptor,
    evaluate_signal_definition,
    validate_expression,
)
from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin, WorkItemType
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, board, context, project, sprint, workitem


def _definition(expression: dict[str, object]) -> SignalDefinition:
    return SignalDefinition(
        name="Scoped stale work",
        entity_type="issue",
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


def test_date_between_condition_matches_datetime_range() -> None:
    item = workitem(created_at=NOW - timedelta(days=5), updated_at=NOW - timedelta(days=4))
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {
                "field": "created_at",
                "operator": "between",
                "value": {
                    "start": (NOW - timedelta(days=7)).isoformat(),
                    "end": (NOW - timedelta(days=3)).isoformat(),
                },
            }
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
    assert findings[0].evidence["created_at"] == item.created_at.isoformat()


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


def test_evaluation_restricted_to_supplied_scope() -> None:
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


def test_no_scope_yields_no_findings() -> None:
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "status_category", "operator": "is", "value": "in_progress"}],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(workitem(),)),
        context(),
        JiraConnector.describe_signal_schema(),
        [],
    )

    assert findings == []


def test_repeated_runs_with_fixed_now_are_identical() -> None:
    item = workitem(created_at=NOW - timedelta(days=5), updated_at=NOW - timedelta(days=4))
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {
                "field": "age_since_created",
                "operator": "greater_than",
                "value": {"amount": 3, "unit": "days"},
            }
        ],
    }
    data = SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,))
    definition = _definition(expression)
    schema = JiraConnector.describe_signal_schema()

    first = evaluate_signal_definition(definition, data, context(), schema, [_scope()])
    second = evaluate_signal_definition(definition, data, context(), schema, [_scope()])

    assert [finding.model_dump(exclude={"id"}) for finding in first] == [
        finding.model_dump(exclude={"id"}) for finding in second
    ]


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
        context(sprint_id=current_sprint.id),
        JiraConnector.describe_signal_schema(),
        [_scope(("sprint", "statuses", "labels"))],
    )

    assert len(findings) == 1
    assert findings[0].evidence["sprint_day"] == 3


# Items with tz-aware UTC created_at used in naive-date-string comparisons.
_CREATED_JAN = datetime(2026, 1, 20, 12, tzinfo=timezone.utc)
_CREATED_AUG = datetime(2026, 8, 1, 0, tzinfo=timezone.utc)


def test_before_date_only_string_true() -> None:
    """before with a date-only rule value must not raise and must return True when observed < rule."""
    item = workitem(created_at=_CREATED_JAN)
    expression = {
        "field": "created_at",
        "operator": "before",
        "value": "2026-06-17",
    }

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1


def test_before_date_only_string_false() -> None:
    """before with a date-only rule value returns False when observed is after the rule date."""
    item = workitem(created_at=_CREATED_AUG)
    expression = {
        "field": "created_at",
        "operator": "before",
        "value": "2026-06-17",
    }

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert findings == []


def test_after_date_only_string_true() -> None:
    """after with a date-only rule value must not raise and must return True when observed > rule."""
    item = workitem(created_at=_CREATED_AUG)
    expression = {
        "field": "created_at",
        "operator": "after",
        "value": "2026-06-17",
    }

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1


def test_after_date_only_string_false() -> None:
    """after with a date-only rule value returns False when observed is before the rule date."""
    item = workitem(created_at=_CREATED_JAN)
    expression = {
        "field": "created_at",
        "operator": "after",
        "value": "2026-06-17",
    }

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert findings == []


def test_between_date_only_strings_true() -> None:
    """between with date-only start/end strings must not raise and match when observed is within range."""
    item = workitem(created_at=_CREATED_JAN)
    expression = {
        "field": "created_at",
        "operator": "between",
        "value": {"start": "2026-01-01", "end": "2026-06-30"},
    }

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1


def test_between_date_only_strings_false() -> None:
    """between with date-only start/end strings returns False when observed is outside the range."""
    item = workitem(created_at=_CREATED_AUG)
    expression = {
        "field": "created_at",
        "operator": "between",
        "value": {"start": "2026-01-01", "end": "2026-06-30"},
    }

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert findings == []


def test_has_epic_parent_true_when_parent_is_epic() -> None:
    """has_epic_parent returns True for a story whose parent is an Epic."""
    epic = workitem(key="RAD-0", item_type=WorkItemType.EPIC)
    story = workitem(key="RAD-1", parent_id=epic.id)
    expression = {"field": "has_epic_parent", "operator": "is", "value": True}

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(epic, story)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == story.id


def test_has_epic_parent_false_when_no_parent() -> None:
    """has_epic_parent returns False for a story with no parent."""
    story = workitem(key="RAD-1", parent_id=None)
    expression = {"field": "has_epic_parent", "operator": "is", "value": False}

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(story,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1


def test_has_epic_parent_false_when_parent_is_not_epic() -> None:
    """has_epic_parent returns False for a story whose parent is a Story (not Epic)."""
    parent_story = workitem(key="RAD-0", item_type=WorkItemType.STORY)
    child = workitem(key="RAD-1", parent_id=parent_story.id)
    expression = {"field": "has_epic_parent", "operator": "is", "value": False}

    findings = evaluate_signal_definition(
        _definition({"type": "group", "operator": "all", "conditions": [expression]}),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(parent_story, child)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 2
