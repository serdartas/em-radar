from datetime import timedelta
from uuid import uuid4

from em_radar_core.models import Severity
from em_radar_core.signals import SignalData, SprintScopeChurnSignal

from _signal_helpers import NOW, context, sprint, transition, workitem


def test_churn_above_warning_threshold_fires_warning() -> None:
    current = sprint("Sprint 1", start_date=NOW - timedelta(days=7))
    original = workitem("RAD-1", sprint_ids=[current.id], created_at=NOW - timedelta(days=8))
    added = workitem("RAD-2", sprint_ids=[current.id], created_at=NOW - timedelta(days=6))

    findings = SprintScopeChurnSignal({"warning_pct": 20.0, "critical_pct": 120.0}).evaluate(
        SignalData(report_id=uuid4(), sprints=(current,), workitems=(original, added)),
        context(current.id),
    )

    assert SprintScopeChurnSignal.sprint_only is True
    assert len(findings) == 1
    assert findings[0].severity is Severity.WARNING
    assert findings[0].evidence == {
        "original_count": 1,
        "added_count": 1,
        "churn_pct": 100.0,
    }


def test_churn_above_critical_threshold_escalates_to_critical() -> None:
    current = sprint("Sprint 1", start_date=NOW - timedelta(days=7))
    original = workitem("RAD-1", sprint_ids=[current.id], created_at=NOW - timedelta(days=8))
    added = workitem("RAD-2", sprint_ids=[current.id], created_at=NOW - timedelta(days=6))

    findings = SprintScopeChurnSignal({"warning_pct": 20.0, "critical_pct": 35.0}).evaluate(
        SignalData(report_id=uuid4(), sprints=(current,), workitems=(original, added)),
        context(current.id),
    )

    assert len(findings) == 1
    assert findings[0].severity is Severity.CRITICAL
    assert findings[0].evidence == {
        "original_count": 1,
        "added_count": 1,
        "churn_pct": 100.0,
    }


def test_transition_history_can_supply_first_seen_time() -> None:
    current = sprint("Sprint 1", start_date=NOW - timedelta(days=7))
    original = workitem("RAD-1", sprint_ids=[current.id], created_at=None, updated_at=None)
    added = workitem("RAD-2", sprint_ids=[current.id], created_at=None, updated_at=None)

    findings = SprintScopeChurnSignal({"warning_pct": 20.0, "critical_pct": 120.0}).evaluate(
        SignalData(
            report_id=uuid4(),
            sprints=(current,),
            workitems=(original, added),
            transitions=(
                transition(
                    original.id,
                    occurred_at=NOW - timedelta(days=8),
                    to_status_category=original.status_category,
                ),
                transition(
                    added.id,
                    occurred_at=NOW - timedelta(days=6),
                    to_status_category=added.status_category,
                ),
            ),
        ),
        context(current.id),
    )

    assert len(findings) == 1
    assert findings[0].evidence == {
        "original_count": 1,
        "added_count": 1,
        "churn_pct": 100.0,
    }
