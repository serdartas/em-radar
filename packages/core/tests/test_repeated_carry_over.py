from uuid import uuid4

from em_radar_core.models import StatusCategory
from em_radar_core.signals import RepeatedCarryOverSignal, SignalData

from _signal_helpers import context, sprint, workitem


def test_item_in_multiple_sprints_fires_with_sprint_names() -> None:
    first = sprint("Sprint 1")
    second = sprint("Sprint 2")
    item = workitem("RAD-1", sprint_ids=[first.id, second.id], current_sprint_id=second.id)

    findings = RepeatedCarryOverSignal().evaluate(
        SignalData(report_id=uuid4(), sprints=(first, second), workitems=(item,)),
        context(second.id),
    )

    assert RepeatedCarryOverSignal.sprint_only is True
    assert len(findings) == 1
    assert findings[0].evidence == {
        "sprint_count": 2,
        "sprint_names": ["Sprint 1", "Sprint 2"],
    }


def test_single_sprint_item_does_not_fire() -> None:
    current = sprint("Sprint 2")
    item = workitem("RAD-1", sprint_ids=[current.id], current_sprint_id=current.id)

    findings = RepeatedCarryOverSignal().evaluate(
        SignalData(report_id=uuid4(), sprints=(current,), workitems=(item,)),
        context(current.id),
    )

    assert findings == []


def test_completed_item_does_not_fire() -> None:
    first = sprint("Sprint 1")
    second = sprint("Sprint 2")
    item = workitem(
        "RAD-1",
        status="Done",
        status_category=StatusCategory.DONE,
        sprint_ids=[first.id, second.id],
        current_sprint_id=second.id,
    )

    findings = RepeatedCarryOverSignal().evaluate(
        SignalData(report_id=uuid4(), sprints=(first, second), workitems=(item,)),
        context(second.id),
    )

    assert findings == []
