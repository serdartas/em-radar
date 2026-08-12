"""Tests for capability-based signal skipping (connector spec §5, §6.5)."""

from datetime import timedelta
from uuid import uuid4

from em_radar_core.connectors import Capabilities
from em_radar_core.evaluation import (
    ScopeDescriptor,
    SignalSkipNote,
    check_capability_gate,
    evaluate_signal_definition,
)
from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, context, project, workitem


def _scope(*, connector_capabilities: Capabilities | None = None) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Radar",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "RAD", "name": "Radar"},
        capabilities=("statuses", "labels"),
        connector_capabilities=connector_capabilities,
    )


def _history_signal() -> SignalDefinition:
    """A signal that uses age_in_current_status — requires transitions for accurate results."""
    return SignalDefinition(
        name="History signal",
        entity_type="issue",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is", "value": "in_progress"},
                {
                    "field": "age_in_current_status",
                    "operator": "greater_than",
                    "value": {"amount": 7, "unit": "days"},
                },
            ],
        },
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _simple_signal() -> SignalDefinition:
    """A signal that uses only basic fields — no connector capabilities required."""
    return SignalDefinition(
        name="Simple signal",
        entity_type="issue",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is", "value": "in_progress"},
            ],
        },
        report_settings=ReportSettings(severity="info", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


# ---------------------------------------------------------------------------
# check_capability_gate unit tests
# ---------------------------------------------------------------------------


def test_history_signal_skipped_when_transitions_unavailable() -> None:
    caps = Capabilities(provides_workitems=True, provides_transitions=False)
    definition = _history_signal()

    note = check_capability_gate(definition, caps)

    assert isinstance(note, SignalSkipNote)
    assert note.signal_id == str(definition.id)
    assert "provides_transitions" in note.reason


def test_history_signal_not_skipped_when_transitions_available() -> None:
    caps = Capabilities(provides_workitems=True, provides_transitions=True)

    note = check_capability_gate(_history_signal(), caps)

    assert note is None


def test_simple_signal_not_skipped_regardless_of_transitions() -> None:
    caps = Capabilities(provides_workitems=True, provides_transitions=False)

    note = check_capability_gate(_simple_signal(), caps)

    assert note is None


# ---------------------------------------------------------------------------
# Integration: evaluate_signal_definition skips when capability is absent
# ---------------------------------------------------------------------------


def test_evaluate_skips_history_signal_when_transitions_unavailable() -> None:
    item = workitem(key="RAD-1", updated_at=NOW - timedelta(days=10))
    caps = Capabilities(provides_workitems=True, provides_transitions=False)

    findings = evaluate_signal_definition(
        _history_signal(),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope(connector_capabilities=caps)],
    )

    assert findings == []


def test_evaluate_runs_history_signal_when_transitions_available() -> None:
    item = workitem(key="RAD-1", updated_at=NOW - timedelta(days=10))
    caps = Capabilities(provides_workitems=True, provides_transitions=True)

    findings = evaluate_signal_definition(
        _history_signal(),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope(connector_capabilities=caps)],
    )

    assert len(findings) == 1


def test_evaluate_runs_history_signal_when_no_capability_info_provided() -> None:
    """When connector_capabilities is None, the gate is not applied."""
    item = workitem(key="RAD-1", updated_at=NOW - timedelta(days=10))

    findings = evaluate_signal_definition(
        _history_signal(),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1


def test_evaluate_runs_simple_signal_when_transitions_unavailable() -> None:
    item = workitem(key="RAD-1")
    caps = Capabilities(provides_workitems=True, provides_transitions=False)

    findings = evaluate_signal_definition(
        _simple_signal(),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope(connector_capabilities=caps)],
    )

    assert len(findings) == 1
