from uuid import uuid4

from em_radar_core.models import WorkItemType
from em_radar_core.signals import EpicTooBroadSignal, SignalData

from _signal_helpers import context, workitem


def test_epic_over_threshold_fires_with_child_count() -> None:
    epic = workitem("RAD-1", item_type=WorkItemType.EPIC, acceptance_criteria=None)
    children = tuple(workitem(f"RAD-{number}", parent_id=epic.id) for number in range(2, 6))

    findings = EpicTooBroadSignal({"max_children": 3}).evaluate(
        SignalData(report_id=uuid4(), workitems=(epic, *children)),
        context(),
    )

    assert len(findings) == 1
    assert findings[0].evidence == {"child_count": 4, "threshold": 3}


def test_epic_at_or_under_threshold_does_not_fire() -> None:
    epic = workitem("RAD-1", item_type=WorkItemType.EPIC, acceptance_criteria=None)
    children = tuple(workitem(f"RAD-{number}", parent_id=epic.id) for number in range(2, 5))

    findings = EpicTooBroadSignal({"max_children": 3}).evaluate(
        SignalData(report_id=uuid4(), workitems=(epic, *children)),
        context(),
    )

    assert findings == []
