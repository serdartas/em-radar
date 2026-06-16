from datetime import timedelta
from uuid import uuid4

from em_radar_core.models import StatusCategory
from em_radar_core.signals import BlockedWithoutUpdateSignal, SignalData

from _signal_helpers import NOW, context, transition, workitem


def test_blocked_and_idle_items_fire_with_evidence() -> None:
    item = workitem(
        "RAD-1",
        is_blocked=True,
        updated_at=NOW - timedelta(days=4, hours=1),
    )

    findings = BlockedWithoutUpdateSignal().evaluate(
        SignalData(report_id=uuid4(), workitems=(item,)),
        context(),
    )

    assert len(findings) == 1
    assert findings[0].evidence == {
        "days_blocked_idle": 4,
        "last_updated_at": (NOW - timedelta(days=4, hours=1)).isoformat(),
        "threshold": 3,
    }


def test_recently_updated_blocked_items_do_not_fire() -> None:
    item = workitem("RAD-2", is_blocked=True, updated_at=NOW - timedelta(days=1))

    findings = BlockedWithoutUpdateSignal().evaluate(
        SignalData(report_id=uuid4(), workitems=(item,)),
        context(),
    )

    assert findings == []


def test_blocked_transition_is_used_when_item_update_is_missing() -> None:
    item = workitem("RAD-3", updated_at=None)
    blocked_transition = transition(
        item.id,
        occurred_at=NOW - timedelta(days=5),
        to_status_category=StatusCategory.BLOCKED,
    )

    findings = BlockedWithoutUpdateSignal().evaluate(
        SignalData(report_id=uuid4(), workitems=(item,), transitions=(blocked_transition,)),
        context(),
    )

    assert len(findings) == 1
    assert findings[0].evidence == {
        "days_blocked_idle": 5,
        "last_updated_at": (NOW - timedelta(days=5)).isoformat(),
        "threshold": 3,
    }
