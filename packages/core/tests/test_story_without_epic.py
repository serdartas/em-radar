from uuid import uuid4

from em_radar_core.models import WorkItemType
from em_radar_core.signals import StoryWithoutParentEpicSignal, SignalData

from _signal_helpers import context, workitem


def test_stories_without_parent_fire() -> None:
    item = workitem("RAD-1", parent_id=None)

    findings = StoryWithoutParentEpicSignal().evaluate(
        SignalData(report_id=uuid4(), workitems=(item,)),
        context(),
    )

    assert len(findings) == 1
    assert findings[0].evidence == {"workitem_type": "story"}


def test_stories_with_parent_epic_do_not_fire() -> None:
    epic = workitem("RAD-10", item_type=WorkItemType.EPIC, acceptance_criteria=None)
    story = workitem("RAD-2", parent_id=epic.id)

    findings = StoryWithoutParentEpicSignal().evaluate(
        SignalData(report_id=uuid4(), workitems=(epic, story)),
        context(),
    )

    assert findings == []
