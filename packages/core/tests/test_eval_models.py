from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import JSON

from em_radar_core.models import (
    Confidence,
    EntityType,
    EvaluationContext,
    EvaluationWindow,
    Report,
    ReportStatus,
    Severity,
    SignalFinding,
    TeamProfile,
    WindowType,
    WorkingMode,
)


NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def team_profile(**overrides: object) -> TeamProfile:
    values: dict[str, object] = {
        "name": "Platform",
        "project_ids": [uuid4()],
        "repository_ids": [uuid4()],
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return TeamProfile(**values)


def sprint_window(**overrides: object) -> EvaluationWindow:
    values: dict[str, object] = {
        "window_type": WindowType.SPRINT,
        "sprint_id": uuid4(),
        "team_profile_id": uuid4(),
    }
    values.update(overrides)
    return EvaluationWindow(**values)


def finding(**overrides: object) -> SignalFinding:
    values: dict[str, object] = {
        "report_id": uuid4(),
        "signal_id": "stale-in-progress-work-item",
        "signal_name": "Stale in-progress work item",
        "severity": Severity.WARNING,
        "confidence": Confidence.HIGH,
        "entity_type": EntityType.WORKITEM,
        "entity_id": uuid4(),
        "title": "DEMO-1 is stale",
        "reason": "No update for nine days",
        "evidence": {"days_idle": 9, "related": [str(uuid4())], "threshold": None},
        "created_at": NOW,
    }
    values.update(overrides)
    return SignalFinding(**values)


def test_valid_evaluation_entities_can_be_constructed() -> None:
    team = team_profile()
    window = sprint_window(team_profile_id=team.id)
    report = Report(
        evaluation_window_id=window.id,
        signal_pack_snapshot={"signals": []},
        status=ReportStatus.RUNNING,
        started_at=NOW,
    )
    result = finding(report_id=report.id)
    context = EvaluationContext(now=NOW, window=window, team=team)

    assert team.working_mode is WorkingMode.SCRUM
    assert report.findings_count_by_severity == {
        Severity.INFO: 0,
        Severity.WARNING: 0,
        Severity.CRITICAL: 0,
    }
    assert result.uniqueness_key == (
        report.id,
        result.signal_id,
        result.entity_type,
        result.entity_id,
    )
    assert context.now == NOW


@pytest.mark.parametrize(
    "overrides",
    [
        {"sprint_id": None},
        {"start": NOW},
        {"end": NOW},
    ],
)
def test_sprint_window_requires_only_sprint_id(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        sprint_window(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"start": None},
        {"end": None},
        {"sprint_id": UUID(int=1)},
    ],
)
def test_date_range_window_requires_only_start_and_end(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "window_type": WindowType.DATE_RANGE,
        "start": NOW - timedelta(days=14),
        "end": NOW,
        "team_profile_id": uuid4(),
    }
    values.update(overrides)

    with pytest.raises(ValidationError):
        EvaluationWindow(**values)


@pytest.mark.parametrize(
    "evidence",
    [
        {"nested": {"values": [1, "two", True, None]}},
        ["arbitrary", 3, False, None],
        "observed value",
        42,
    ],
)
def test_finding_evidence_accepts_arbitrary_json(evidence: object) -> None:
    assert finding(evidence=evidence).evidence == evidence


def test_evaluation_context_now_is_required() -> None:
    team = team_profile()

    with pytest.raises(ValidationError):
        EvaluationContext(window=sprint_window(team_profile_id=team.id), team=team)


def test_json_fields_use_json_storage_type() -> None:
    for field_name in (
        "connection_ids",
        "project_ids",
        "board_ids",
        "repository_ids",
        "member_user_keys",
    ):
        assert TeamProfile.model_fields[field_name].metadata[0].sa_type is JSON
    assert SignalFinding.model_fields["evidence"].metadata[0].sa_type is JSON
    assert Report.model_fields["signal_pack_snapshot"].metadata[0].sa_type is JSON
    assert Report.model_fields["findings_count_by_severity"].metadata[0].sa_type is JSON


@pytest.mark.parametrize(
    "counts",
    [
        {"info": 0, "warning": 0},
        {"info": 0, "warning": 0, "critical": 0, "other": 0},
        {"info": 0, "warning": -1, "critical": 0},
    ],
)
def test_report_findings_count_shape_is_enforced(counts: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Report(
            evaluation_window_id=uuid4(),
            signal_pack_snapshot={},
            status=ReportStatus.SUCCEEDED,
            started_at=NOW,
            findings_count_by_severity=counts,
        )
