from uuid import uuid4

from em_radar_core.models import WorkItemType
from em_radar_core.signals import EpicWithoutMeasurableDescriptionSignal, SignalData

from _signal_helpers import context, workitem


def test_short_and_empty_epic_descriptions_fire() -> None:
    short = workitem(
        "RAD-1",
        item_type=WorkItemType.EPIC,
        description="short",
        acceptance_criteria=None,
    )
    empty = workitem(
        "RAD-2",
        item_type=WorkItemType.EPIC,
        description=None,
        acceptance_criteria=None,
    )

    findings = EpicWithoutMeasurableDescriptionSignal({"min_description_length": 10}).evaluate(
        SignalData(report_id=uuid4(), workitems=(short, empty)),
        context(),
    )

    assert [finding.evidence for finding in findings] == [
        {"description_length": 5, "threshold": 10},
        {"description_length": 0, "threshold": 10},
    ]


def test_sufficiently_long_epic_description_does_not_fire() -> None:
    epic = workitem(
        "RAD-1",
        item_type=WorkItemType.EPIC,
        description="A measurable outcome with enough detail.",
        acceptance_criteria=None,
    )

    findings = EpicWithoutMeasurableDescriptionSignal({"min_description_length": 10}).evaluate(
        SignalData(report_id=uuid4(), workitems=(epic,)),
        context(),
    )

    assert findings == []
