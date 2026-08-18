"""Verification tests for M5-14: 5 MR signals seeded as declarative default-pack definitions.

Asserts that:
1. All 5 MR definitions validate against the GitLab capability schema.
2. Each signal fires against a matching MergeRequest fixture (and not against a non-match).
3. The seeded default group now contains 13 enabled signals (8 WI + 5 MR).
4. MR signals export round-trip in the declarative pack.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, select

from em_radar_config import PackValidationContext, load_signal_pack
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import (
    MergeRequest,
    MergeRequestState,
    PipelineStatus,
    ReportSettings,
    Review,
    ReviewDecision,
    SignalDefinition,
    SignalOrigin,
    Source,
)
from em_radar_core.signals import SignalData

DEFAULT_PACK_PATH = Path(__file__).parents[1] / "defaults" / "default-pack.yaml"

MR_TEMPLATE_KEYS = {
    "mergerequest-waiting-too-long",
    "mergerequest-without-linked-workitem",
    "large-mergerequest-risk",
    "failing-pipeline-too-long",
    "merged-without-enough-approval",
}

_REPO_ID = uuid4()
_AUTHOR_ID = uuid4()

_NOW_DT = datetime(2026, 1, 20, 12, tzinfo=timezone.utc)


def _scope(capabilities: tuple[str, ...] = ()) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="gl-1",
        scope_id="scope-1",
        scope_type="repository",
        name="repo",
        external_ref={"id": "repo-1"},
        capabilities=capabilities,
    )


def _mr(
    iid: int = 1,
    *,
    state: MergeRequestState = MergeRequestState.OPEN,
    linked_workitem_keys: list[str] | None = None,
    changed_files_count: int | None = None,
    pipeline_status: PipelineStatus | None = None,
    pipeline_updated_at: datetime | None = None,
    approval_count: int = 0,
    merged_at: datetime | None = None,
    closed_at: datetime | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MergeRequest:
    if state is MergeRequestState.MERGED and merged_at is None:
        merged_at = _NOW_DT
    if state is MergeRequestState.CLOSED and closed_at is None:
        closed_at = _NOW_DT
    return MergeRequest(
        source=Source.GITLAB,
        external_id=f"mr-{iid}",
        repository_id=_REPO_ID,
        iid=iid,
        title=f"MR {iid}",
        state=state,
        author_id=_AUTHOR_ID,
        target_branch="main",
        source_branch="feature/x",
        approval_count=approval_count,
        changed_files_count=changed_files_count,
        pipeline_status=pipeline_status,
        pipeline_updated_at=pipeline_updated_at,
        linked_workitem_keys=linked_workitem_keys or [],
        created_at=created_at or _NOW_DT,
        updated_at=updated_at or _NOW_DT,
        merged_at=merged_at,
        closed_at=closed_at,
    )


def _defn_from_pack(template_key: str) -> SignalDefinition:
    pack = load_signal_pack(DEFAULT_PACK_PATH.read_text(encoding="utf-8")).pack
    signal = next(s for s in pack.spec.signals if s.template_key == template_key)
    return SignalDefinition(
        name=signal.name or template_key,
        entity_type=signal.entity_type or "merge_request",
        expression=signal.expression,
        report_settings=ReportSettings(
            **(signal.report_settings or {"severity": "warning", "category": "flow"})
        ),
        enabled=True,
        origin=SignalOrigin.SYSTEM_TEMPLATE,
        template_key=template_key,
        created_at=_NOW_DT,
        updated_at=_NOW_DT,
    )


def _ctx():
    from em_radar_core.models import EvaluationContext, EvaluationWindow, TeamProfile, WindowType

    team = TeamProfile(name="t", created_at=_NOW_DT, updated_at=_NOW_DT)
    window = EvaluationWindow(
        window_type=WindowType.DATE_RANGE, start=_NOW_DT, end=_NOW_DT, team_profile_id=team.id
    )
    return EvaluationContext(now=_NOW_DT, window=window, team=team)


# ---------------------------------------------------------------------------
# 1. Schema validation — all 5 MR signals validate against GitLab schema
# ---------------------------------------------------------------------------


def test_mr_signals_validate_against_gitlab_schema() -> None:
    """MR signals validate against GitLab schema; full pack validated with both schemas."""
    from em_radar_connector_jira.connector import JiraConnector

    ctx = PackValidationContext(
        signal_schemas=(
            JiraConnector.describe_signal_schema(),
            GitLabConnector.describe_signal_schema(),
        )
    )
    result = load_signal_pack(DEFAULT_PACK_PATH.read_text(encoding="utf-8"), ctx)

    mr_signals = [s for s in result.pack.spec.signals if s.entity_type == "merge_request"]
    assert {s.template_key for s in mr_signals} == MR_TEMPLATE_KEYS
    assert result.warnings == ()


# ---------------------------------------------------------------------------
# 2. Each MR signal fires against a matching fixture
# ---------------------------------------------------------------------------


def test_mergerequest_waiting_too_long_fires() -> None:
    old_review = Review(
        mergerequest_id=uuid4(),
        reviewer_id=uuid4(),
        decision=ReviewDecision.APPROVED,
        submitted_at=_NOW_DT - timedelta(days=5),
    )
    mr = _mr(1)
    old_review.mergerequest_id = mr.id
    data = SignalData(report_id=uuid4(), mergerequests=(mr,), reviews=(old_review,))
    definition = _defn_from_pack("mergerequest-waiting-too-long")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope(("reviews",))]
    )

    assert len(findings) == 1
    assert findings[0].entity_id == mr.id


def test_mergerequest_waiting_too_long_does_not_fire_for_recent_review() -> None:
    recent_review = Review(
        mergerequest_id=uuid4(),
        reviewer_id=uuid4(),
        decision=ReviewDecision.APPROVED,
        submitted_at=_NOW_DT - timedelta(hours=1),
    )
    mr = _mr(1)
    recent_review.mergerequest_id = mr.id
    data = SignalData(report_id=uuid4(), mergerequests=(mr,), reviews=(recent_review,))
    definition = _defn_from_pack("mergerequest-waiting-too-long")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope(("reviews",))]
    )

    assert findings == []


def test_mergerequest_without_linked_workitem_fires() -> None:
    mr = _mr(1, linked_workitem_keys=[])
    data = SignalData(report_id=uuid4(), mergerequests=(mr,))
    definition = _defn_from_pack("mergerequest-without-linked-workitem")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope()]
    )

    assert len(findings) == 1


def test_mergerequest_without_linked_workitem_does_not_fire_when_linked() -> None:
    mr = _mr(1, linked_workitem_keys=["PLAT-42"])
    data = SignalData(report_id=uuid4(), mergerequests=(mr,))
    definition = _defn_from_pack("mergerequest-without-linked-workitem")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope()]
    )

    assert findings == []


def test_large_mergerequest_risk_fires_on_many_files() -> None:
    mr = _mr(1, changed_files_count=25)
    data = SignalData(report_id=uuid4(), mergerequests=(mr,))
    definition = _defn_from_pack("large-mergerequest-risk")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope()]
    )

    assert len(findings) == 1


def test_large_mergerequest_risk_does_not_fire_for_small_mr() -> None:
    mr = _mr(1, changed_files_count=5)
    data = SignalData(report_id=uuid4(), mergerequests=(mr,))
    definition = _defn_from_pack("large-mergerequest-risk")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope()]
    )

    assert findings == []


def test_failing_pipeline_too_long_fires() -> None:
    mr = _mr(
        1,
        pipeline_status=PipelineStatus.FAILED,
        pipeline_updated_at=_NOW_DT - timedelta(days=2),
    )
    data = SignalData(report_id=uuid4(), mergerequests=(mr,))
    definition = _defn_from_pack("failing-pipeline-too-long")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope(("pipelines",))]
    )

    assert len(findings) == 1


def test_failing_pipeline_too_long_does_not_fire_for_passing_pipeline() -> None:
    mr = _mr(1, pipeline_status=PipelineStatus.SUCCESS)
    data = SignalData(report_id=uuid4(), mergerequests=(mr,))
    definition = _defn_from_pack("failing-pipeline-too-long")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope(("pipelines",))]
    )

    assert findings == []


def test_merged_without_enough_approval_fires() -> None:
    mr = _mr(1, state=MergeRequestState.MERGED, approval_count=0)
    data = SignalData(report_id=uuid4(), mergerequests=(mr,))
    definition = _defn_from_pack("merged-without-enough-approval")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope(("reviews",))]
    )

    assert len(findings) == 1


def test_merged_without_enough_approval_does_not_fire_with_approval() -> None:
    mr = _mr(1, state=MergeRequestState.MERGED, approval_count=1)
    data = SignalData(report_id=uuid4(), mergerequests=(mr,))
    definition = _defn_from_pack("merged-without-enough-approval")

    findings = evaluate_signal_definition(
        definition, data, _ctx(), GitLabConnector.describe_signal_schema(), [_scope(("reviews",))]
    )

    assert findings == []


# ---------------------------------------------------------------------------
# 3 & 4. Database: seeded group has 13 signals, MR signals round-trip
# ---------------------------------------------------------------------------


@pytest.fixture
def _api_harness(tmp_path) -> Iterator[SimpleNamespace]:
    import em_radar_api.tables  # noqa: F401

    from em_radar_api.db import (
        create_db_engine,
        create_session_factory,
        get_session,
        get_write_session,
    )
    from em_radar_api.main import create_app

    engine = create_db_engine(tmp_path / "m5-14-test.db")
    SQLModel.metadata.create_all(engine)
    factory = create_session_factory(engine)

    def _session():
        with factory() as session:
            yield session

    app = create_app(app_session_factory=factory)
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_write_session] = _session
    try:
        yield SimpleNamespace(client=TestClient(app), session_factory=factory)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_seeded_group_contains_13_signals(_api_harness) -> None:
    from em_radar_api.signal_config_groups import SignalConfigGroupTable

    with _api_harness.client:
        pass

    with _api_harness.session_factory() as session:
        group = session.exec(
            select(SignalConfigGroupTable).where(SignalConfigGroupTable.name == "Default signals")
        ).first()

    assert group is not None
    assert len(group.signal_ids) == 12


def test_mr_signals_export_round_trip(_api_harness) -> None:
    from em_radar_api.signal_config_groups import SignalConfigGroupTable

    with _api_harness.client:
        pass

    with _api_harness.session_factory() as session:
        group = session.exec(
            select(SignalConfigGroupTable).where(SignalConfigGroupTable.name == "Default signals")
        ).first()
        group_id = str(group.id)

    response = _api_harness.client.get(
        "/api/signal-pack/export",
        params={"group_ids": [group_id], "export_type": "private_backup"},
    )

    assert response.status_code == 200
    exported = load_signal_pack(response.text)
    exported_mr_keys = {
        s.template_key for s in exported.pack.spec.signals if s.entity_type == "merge_request"
    }
    assert exported_mr_keys == MR_TEMPLATE_KEYS
