from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from em_radar_core.evaluation import SignalConfig, SignalEvaluator
from em_radar_core.models import (
    EntityType,
    Severity,
)
from em_radar_core.signals import SignalData, StaleInProgressSignal, default_registry
from pydantic import ValidationError

from _signal_helpers import NOW, context, workitem


def test_stale_in_progress_emits_findings_and_evidence() -> None:
    stale_1 = workitem("RAD-1", updated_at=NOW - timedelta(days=12))
    stale_2 = workitem("RAD-2", updated_at=NOW - timedelta(days=12))
    fresh = workitem("RAD-3", updated_at=NOW - timedelta(days=3))
    no_updated_at = workitem("RAD-4")

    report_id = uuid4()
    findings = StaleInProgressSignal().evaluate(
        SignalData(report_id=report_id, workitems=(stale_1, stale_2, fresh, no_updated_at)),
        context(),
    )

    assert [f.title.split()[0] for f in findings] == ["RAD-1", "RAD-2"]
    stale_timestamp = (NOW - timedelta(days=12)).isoformat()
    assert all(
        f.report_id == report_id
        and f.signal_id == "stale-in-progress-work-item"
        and f.severity is Severity.WARNING
        and f.entity_type is EntityType.WORKITEM
        and f.created_at == NOW
        and f.evidence == {"days_idle": 12, "last_updated_at": stale_timestamp, "threshold": 7}
        for f in findings
    )


def test_exclude_labels_suppresses_matching_items() -> None:
    labeled = workitem("RAD-1", updated_at=NOW - timedelta(days=12), labels=["area-2"])
    unlabeled_1 = workitem("RAD-2", updated_at=NOW - timedelta(days=12))
    unlabeled_2 = workitem("RAD-3", updated_at=NOW - timedelta(days=12))

    findings = StaleInProgressSignal({"exclude_labels": ["area-2"]}).evaluate(
        SignalData(report_id=uuid4(), workitems=(labeled, unlabeled_1, unlabeled_2)),
        context(),
    )

    assert [f.title.split()[0] for f in findings] == ["RAD-2", "RAD-3"]


def test_evaluator_runs_only_enabled_signals_with_configured_params() -> None:
    stale_1 = workitem("RAD-1", updated_at=NOW - timedelta(days=12))
    stale_2 = workitem("RAD-2", updated_at=NOW - timedelta(days=12))

    findings = SignalEvaluator().evaluate(
        SignalData(report_id=uuid4(), workitems=(stale_1, stale_2)),
        context(),
        [
            SignalConfig(signal_id="stale-in-progress-work-item", enabled=False),
            SignalConfig(
                signal_id="stale-in-progress-work-item",
                params={"days_threshold": 11},
            ),
        ],
    )

    assert len(findings) == 2


def test_evaluator_applies_configured_severity_override() -> None:
    stale = workitem("RAD-1", updated_at=NOW - timedelta(days=12))

    findings = SignalEvaluator().evaluate(
        SignalData(report_id=uuid4(), workitems=(stale,)),
        context(),
        [SignalConfig(signal_id="stale-in-progress-work-item", severity=Severity.CRITICAL)],
    )

    assert findings
    assert {f.severity for f in findings} == {Severity.CRITICAL}


def test_evaluator_runs_registered_signals_by_default() -> None:
    stale = workitem("RAD-1", updated_at=NOW - timedelta(days=12))
    story_no_ac = workitem("RAD-2", acceptance_criteria=None)

    findings = SignalEvaluator().evaluate(
        SignalData(report_id=uuid4(), workitems=(stale, story_no_ac)),
        context(),
    )

    signal_ids = {f.signal_id for f in findings}
    assert "stale-in-progress-work-item" in signal_ids
    assert "story-without-acceptance-criteria" in signal_ids


def test_registry_is_keyed_by_id_and_params_are_validated() -> None:
    assert default_registry.get("stale-in-progress-work-item") is StaleInProgressSignal
    assert "sprint-scope-churn" in default_registry.ids()

    with pytest.raises(ValidationError):
        default_registry.create("stale-in-progress-work-item", {"unknown": True})


def test_signal_code_has_no_direct_current_time_calls() -> None:
    signal_dir = Path(__file__).parents[1] / "src" / "em_radar_core" / "signals"

    for path in signal_dir.glob("*.py"):
        source = path.read_text()
        assert "datetime.now(" not in source
        assert "datetime.utcnow(" not in source
