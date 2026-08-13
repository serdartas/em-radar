"""Tests for window-gating: sprint-field signals skipped on date-range runs."""

from uuid import uuid4

from em_radar_core.evaluation import (
    ScopeDescriptor,
    SignalSkipNote,
    check_window_gate,
    evaluate_signal_definition,
)
from em_radar_core.models import (
    EvaluationWindow,
    ReportSettings,
    SignalDefinition,
    SignalOrigin,
    TeamProfile,
    WindowType,
)
from em_radar_core.models.evaluation import EvaluationContext
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, context, project, workitem


def _date_range_ctx() -> EvaluationContext:
    team = TeamProfile(name="Test team", created_at=NOW, updated_at=NOW)
    window = EvaluationWindow(
        window_type=WindowType.DATE_RANGE,
        start=NOW,
        end=NOW,
        team_profile_id=team.id,
    )
    return EvaluationContext(now=NOW, window=window, team=team)


def _sprint_ctx() -> EvaluationContext:
    return context(sprint_id=uuid4())


def _scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Radar",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "RAD", "name": "Radar"},
        capabilities=("statuses", "labels"),
    )


def _board_scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="board",
        name="Radar Board",
        external_ref={"id": "BOARD", "key": "RAD"},
        capabilities=("statuses", "labels", "sprint"),
    )


def _sprint_count_signal() -> SignalDefinition:
    return SignalDefinition(
        name="Sprint count signal",
        entity_type="issue",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is", "value": "in_progress"},
                {"field": "sprint_count", "operator": "greater_than", "value": 1},
            ],
        },
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.SYSTEM_TEMPLATE,
        created_at=NOW,
        updated_at=NOW,
    )


def _non_sprint_signal() -> SignalDefinition:
    return SignalDefinition(
        name="Non-sprint signal",
        entity_type="issue",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is", "value": "in_progress"},
            ],
        },
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


# ---------------------------------------------------------------------------
# check_window_gate unit tests
# ---------------------------------------------------------------------------


def test_sprint_count_field_skipped_on_date_range() -> None:
    definition = _sprint_count_signal()
    note = check_window_gate(definition, _date_range_ctx())

    assert isinstance(note, SignalSkipNote)
    assert note.signal_id == str(definition.id)
    assert "sprint window" in note.reason


def test_sprint_day_field_skipped_on_date_range() -> None:
    definition = SignalDefinition(
        name="Sprint day signal",
        entity_type="issue",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "sprint_day", "operator": "is", "value": 1}],
        },
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )
    note = check_window_gate(definition, _date_range_ctx())

    assert isinstance(note, SignalSkipNote)
    assert "sprint window" in note.reason


def test_sprint_fields_not_skipped_on_sprint_window() -> None:
    definition = _sprint_count_signal()
    note = check_window_gate(definition, _sprint_ctx())

    assert note is None


def test_non_sprint_signal_not_gated() -> None:
    note = check_window_gate(_non_sprint_signal(), _date_range_ctx())
    assert note is None


def test_signal_without_expression_not_gated() -> None:
    definition = SignalDefinition(
        name="No expression",
        entity_type="issue",
        expression=None,
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )
    note = check_window_gate(definition, _date_range_ctx())
    assert note is None


# ---------------------------------------------------------------------------
# Integration: evaluate_signal_definition skips on date-range
# ---------------------------------------------------------------------------


def test_date_range_run_skips_sprint_count_signal() -> None:
    item = workitem(key="RAD-1")
    findings = evaluate_signal_definition(
        _sprint_count_signal(),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        _date_range_ctx(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert findings == []


def test_sprint_run_evaluates_non_sprint_signal_normally() -> None:
    item = workitem(key="RAD-1")
    findings = evaluate_signal_definition(
        _non_sprint_signal(),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        _sprint_ctx(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
