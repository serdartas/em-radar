from uuid import uuid4

from em_radar_core.models import WorkItemType
from em_radar_core.signals import StoryWithoutAcceptanceCriteriaSignal, SignalData

from _signal_helpers import context, workitem


def test_stories_without_acceptance_criteria_fire() -> None:
    item = workitem("RAD-1", acceptance_criteria=" ", description="Useful context")

    findings = StoryWithoutAcceptanceCriteriaSignal().evaluate(
        SignalData(report_id=uuid4(), workitems=(item,)),
        context(),
    )

    assert len(findings) == 1
    assert findings[0].evidence == {"workitem_type": "story", "has_description": True}


def test_stories_with_acceptance_criteria_do_not_fire() -> None:
    item = workitem("RAD-2", acceptance_criteria="Given a user, when they save, then it works")

    findings = StoryWithoutAcceptanceCriteriaSignal().evaluate(
        SignalData(report_id=uuid4(), workitems=(item,)),
        context(),
    )

    assert findings == []


def test_non_story_types_are_ignored() -> None:
    item = workitem(
        "RAD-3",
        item_type=WorkItemType.TASK,
        acceptance_criteria=None,
        description=None,
    )

    findings = StoryWithoutAcceptanceCriteriaSignal().evaluate(
        SignalData(report_id=uuid4(), workitems=(item,)),
        context(),
    )

    assert findings == []
