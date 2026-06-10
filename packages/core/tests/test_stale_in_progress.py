from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from em_radar_connector_demo.fixtures import FIXTURE_NOW, build_fixtures
from em_radar_core.evaluation import SignalConfig, SignalEvaluator
from em_radar_core.models import (
    EntityType,
    EvaluationContext,
    EvaluationWindow,
    Severity,
    TeamProfile,
    WindowType,
)
from em_radar_core.signals import SignalData, StaleInProgressSignal, default_registry
from pydantic import ValidationError


def evaluation_context() -> EvaluationContext:
    fixtures = build_fixtures()
    team = TeamProfile(
        name="Demo team",
        project_ids=[project.id for project in fixtures.projects],
        repository_ids=[repository.id for repository in fixtures.repositories],
        created_at=FIXTURE_NOW,
        updated_at=FIXTURE_NOW,
    )
    window = EvaluationWindow(
        window_type=WindowType.SPRINT,
        sprint_id=fixtures.sprints[-1].id,
        team_profile_id=team.id,
    )
    return EvaluationContext(now=FIXTURE_NOW, window=window, team=team)


def test_stale_in_progress_emits_exact_demo_findings_and_evidence() -> None:
    fixtures = build_fixtures()
    report_id = uuid4()
    findings = StaleInProgressSignal().evaluate(
        SignalData(report_id=report_id, workitems=fixtures.workitems),
        evaluation_context(),
    )

    assert [finding.title.split()[0] for finding in findings] == [
        "PLAT-2",
        "PLAT-4",
        "PLAT-8",
        "CHECK-16",
        "MOB-22",
    ]
    assert all(
        finding.report_id == report_id
        and finding.signal_id == "stale-in-progress-work-item"
        and finding.severity is Severity.WARNING
        and finding.entity_type is EntityType.WORKITEM
        and finding.created_at == FIXTURE_NOW
        and finding.evidence
        == {
            "days_idle": 12,
            "last_updated_at": (FIXTURE_NOW - timedelta(days=12)).isoformat(),
            "threshold": 7,
        }
        for finding in findings
    )


def test_exclude_labels_suppresses_matching_items() -> None:
    fixtures = build_fixtures()
    findings = StaleInProgressSignal({"exclude_labels": ["area-2"]}).evaluate(
        SignalData(report_id=uuid4(), workitems=fixtures.workitems),
        evaluation_context(),
    )

    assert [finding.title.split()[0] for finding in findings] == ["PLAT-2", "PLAT-8"]


def test_evaluator_runs_only_enabled_signals_with_configured_params() -> None:
    fixtures = build_fixtures()
    findings = SignalEvaluator().evaluate(
        SignalData(report_id=uuid4(), workitems=fixtures.workitems),
        evaluation_context(),
        [
            SignalConfig(signal_id="stale-in-progress-work-item", enabled=False),
            SignalConfig(
                signal_id="stale-in-progress-work-item",
                params={"days_threshold": 11},
            ),
        ],
    )

    assert len(findings) == 5


def test_evaluator_runs_registered_signals_by_default() -> None:
    fixtures = build_fixtures()

    findings = SignalEvaluator().evaluate(
        SignalData(report_id=uuid4(), workitems=fixtures.workitems),
        evaluation_context(),
    )

    assert len(findings) == 5


def test_registry_is_keyed_by_id_and_params_are_validated() -> None:
    assert default_registry.get("stale-in-progress-work-item") is StaleInProgressSignal

    with pytest.raises(ValidationError):
        default_registry.create("stale-in-progress-work-item", {"unknown": True})


def test_signal_code_has_no_direct_current_time_calls() -> None:
    signal_dir = Path(__file__).parents[1] / "src" / "em_radar_core" / "signals"

    for path in signal_dir.glob("*.py"):
        source = path.read_text()
        assert "datetime.now(" not in source
        assert "datetime.utcnow(" not in source
