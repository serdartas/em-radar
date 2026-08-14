"""Evidence conformance tests (M5-04).

Parametrized over all 13 seeded default signals. Asserts:
1. A firing fixture produces evidence whose keys are exactly the fields its expression references
   (plus `scope_id` for WI/sprint signals). This is the generic evidence contract established in
   M5-11: {field_key: observed_value} for each matched condition, with no hardcoded per-signal
   evidence maps.
2. Evidence is stable — no extra or missing keys relative to the expression.
3. confidence is HIGH for every deterministic signal (data model §6.6).
4. No template_key == branches exist in declarative.py (M5-11 invariant).

Note: The generic builder emits observed expression-field values, not the legacy threshold/alias
keys documented in signal spec §12 (those described the now-deleted _template_evidence() function).
The spec §12 evidence shapes will be updated in a follow-up doc ticket.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import (
    Confidence,
    EvaluationContext,
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    PipelineStatus,
    ReportSettings,
    Review,
    ReviewDecision,
    SignalDefinition,
    SignalOrigin,
    Source,
    SprintState,
    StatusCategory,
    TeamProfile,
    WindowType,
    WorkItem,
    WorkItemType,
)
from em_radar_core.signals import SignalData
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_connector_jira.connector import JiraConnector
from em_radar_config import load_signal_pack

DEFAULT_PACK_PATH = (
    Path(__file__).parents[3] / "packages" / "config" / "defaults" / "default-pack.yaml"
)

NOW = datetime(2026, 1, 20, 12, tzinfo=timezone.utc)
PROJECT_ID = uuid4()
BOARD_ID = uuid4()
REPO_ID = uuid4()
AUTHOR_ID = uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _defn(template_key: str) -> SignalDefinition:
    """Load a signal definition from the default pack by template_key."""
    pack = load_signal_pack(DEFAULT_PACK_PATH.read_text(encoding="utf-8")).pack
    signal = next(s for s in pack.spec.signals if s.template_key == template_key)
    return SignalDefinition(
        name=signal.name or template_key,
        entity_type=signal.entity_type or "issue",
        expression=signal.expression,
        report_settings=ReportSettings(
            **(signal.report_settings or {"severity": "warning", "category": "flow"})
        ),
        enabled=True,
        origin=SignalOrigin.SYSTEM_TEMPLATE,
        template_key=template_key,
        created_at=NOW,
        updated_at=NOW,
    )


def _ctx(sprint_id: str | None = None) -> EvaluationContext:

    team = TeamProfile(name="t", created_at=NOW, updated_at=NOW)
    if sprint_id is not None:
        window = EvaluationWindow(
            window_type=WindowType.SPRINT, sprint_id=sprint_id, team_profile_id=team.id
        )
    else:
        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE, start=NOW, end=NOW, team_profile_id=team.id
        )
    return EvaluationContext(now=NOW, window=window, team=team)


def _wi_scope(capabilities: tuple[str, ...] = ()) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="proj",
        external_ref={"id": "PROJECT", "key": "RAD"},
        capabilities=("statuses", "labels", *capabilities),
    )


def _board_scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="board",
        name="board",
        external_ref={"id": "BOARD", "key": "RAD"},
        capabilities=("statuses", "labels", "sprint"),
    )


def _mr_scope(capabilities: tuple[str, ...] = ()) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="gl-1",
        scope_id="scope-1",
        scope_type="repository",
        name="repo",
        external_ref={"id": "repo-1"},
        capabilities=capabilities,
    )


def _workitem(
    key: str = "RAD-1",
    item_type: WorkItemType = WorkItemType.STORY,
    status_category: StatusCategory = StatusCategory.IN_PROGRESS,
    status: str = "In Progress",
    labels: list[str] | None = None,
    parent_id: UUID | None = None,
    acceptance_criteria: str | None = "Given When Then",
    description: str | None = "Description",
    sprint_ids: list[UUID] | None = None,
    current_sprint_id: UUID | None = None,
    updated_at: datetime | None = None,
    created_at: datetime | None = None,
) -> WorkItem:
    return WorkItem(
        source=Source.JIRA,
        external_id=key,
        project_id=PROJECT_ID,
        key=key,
        type=item_type,
        title=f"{key} title",
        description=description,
        status=status,
        status_category=status_category,
        labels=labels or [],
        parent_id=parent_id,
        acceptance_criteria=acceptance_criteria,
        sprint_ids=sprint_ids or [],
        current_sprint_id=current_sprint_id,
        resolved_at=NOW if status_category is StatusCategory.DONE else None,
        created_at=created_at or NOW,
        updated_at=updated_at or NOW,
    )


def _mr(
    iid: int = 1,
    state: MergeRequestState = MergeRequestState.OPEN,
    linked_workitem_keys: list[str] | None = None,
    changed_files_count: int | None = None,
    pipeline_status: PipelineStatus | None = None,
    pipeline_updated_at: datetime | None = None,
    approval_count: int | None = None,
    merged_at: datetime | None = None,
) -> MergeRequest:
    if state is MergeRequestState.MERGED and merged_at is None:
        merged_at = NOW
    return MergeRequest(
        source=Source.GITLAB,
        external_id=f"mr-{iid}",
        repository_id=REPO_ID,
        iid=iid,
        title=f"MR {iid}",
        state=state,
        author_id=AUTHOR_ID,
        target_branch="main",
        source_branch="feature/x",
        approval_count=approval_count,
        changed_files_count=changed_files_count,
        pipeline_status=pipeline_status,
        pipeline_updated_at=pipeline_updated_at,
        linked_workitem_keys=linked_workitem_keys or [],
        created_at=NOW,
        updated_at=NOW,
        merged_at=merged_at,
    )


def _sprint(name: str = "Sprint 1", start_date: datetime | None = None):
    from em_radar_core.models import Sprint

    return Sprint(
        source=Source.JIRA,
        external_id=name,
        board_id=BOARD_ID,
        name=name,
        state=SprintState.ACTIVE,
        start_date=start_date,
    )


def _board():
    from em_radar_core.models import Board

    return Board(
        id=BOARD_ID,
        source=Source.JIRA,
        external_id="BOARD",
        project_id=PROJECT_ID,
        name="Board",
    )


def _project():
    from em_radar_core.models import Project

    return Project(
        id=PROJECT_ID,
        source=Source.JIRA,
        external_id="PROJECT",
        key="RAD",
        name="Radar",
    )


# ---------------------------------------------------------------------------
# Fixtures for each signal
# ---------------------------------------------------------------------------


def _stale_fixture():
    item = _workitem(updated_at=NOW - timedelta(days=10))
    return (
        SignalData(report_id=uuid4(), projects=(_project(),), workitems=(item,)),
        _ctx(),
        JiraConnector.describe_signal_schema(),
        [_wi_scope()],
        {"status_category", "age_in_current_status"},
    )


def _blocked_fixture():
    item = _workitem(
        status_category=StatusCategory.BLOCKED, status="Blocked", updated_at=NOW - timedelta(days=5)
    )
    return (
        SignalData(report_id=uuid4(), projects=(_project(),), workitems=(item,)),
        _ctx(),
        JiraConnector.describe_signal_schema(),
        [_wi_scope()],
        {"status_category", "age_since_updated"},
    )


def _no_ac_fixture():
    item = _workitem(item_type=WorkItemType.STORY, acceptance_criteria=None)
    return (
        SignalData(report_id=uuid4(), projects=(_project(),), workitems=(item,)),
        _ctx(),
        JiraConnector.describe_signal_schema(),
        [_wi_scope()],
        {"issue_type", "acceptance_criteria"},
    )


def _no_epic_fixture():
    item = _workitem(item_type=WorkItemType.STORY, parent_id=None)
    return (
        SignalData(report_id=uuid4(), projects=(_project(),), workitems=(item,)),
        _ctx(),
        JiraConnector.describe_signal_schema(),
        [_wi_scope()],
        {"issue_type", "parent_id"},
    )


def _epic_too_broad_fixture():
    epic = _workitem(key="EPIC-1", item_type=WorkItemType.EPIC)
    children = [_workitem(key=f"CHILD-{i}", parent_id=epic.id) for i in range(16)]
    return (
        SignalData(report_id=uuid4(), projects=(_project(),), workitems=(epic, *children)),
        _ctx(),
        JiraConnector.describe_signal_schema(),
        [_wi_scope()],
        {"issue_type", "child_count"},
    )


def _epic_no_description_fixture():
    epic = _workitem(key="EPIC-1", item_type=WorkItemType.EPIC, description="Short")
    return (
        SignalData(report_id=uuid4(), projects=(_project(),), workitems=(epic,)),
        _ctx(),
        JiraConnector.describe_signal_schema(),
        [_wi_scope()],
        {"issue_type", "description_length"},
    )


def _carry_over_fixture():
    s1_id = uuid4()
    s2_id = uuid4()
    item = _workitem(
        sprint_ids=[s1_id, s2_id],
        current_sprint_id=s2_id,
        status_category=StatusCategory.IN_PROGRESS,
    )
    s1 = _sprint("Sprint 1")
    s1.id = s1_id
    s2 = _sprint("Sprint 2")
    s2.id = s2_id
    return (
        SignalData(
            report_id=uuid4(),
            projects=(_project(),),
            boards=(_board(),),
            sprints=(s1, s2),
            workitems=(item,),
        ),
        _ctx(sprint_id=s2_id),
        JiraConnector.describe_signal_schema(),
        [_board_scope()],
        {"status_category", "sprint_count"},
    )


def _churn_fixture():
    s = _sprint("Sprint 1", start_date=NOW - timedelta(days=7))
    original = _workitem(
        key="RAD-1", sprint_ids=[s.id], current_sprint_id=s.id, updated_at=NOW - timedelta(days=8)
    )
    added = _workitem(
        key="RAD-2", sprint_ids=[s.id], current_sprint_id=s.id, updated_at=NOW - timedelta(days=2)
    )
    from em_radar_core.models import Transition, EntityType

    t1 = Transition(
        entity_type=EntityType.WORKITEM,
        entity_id=original.id,
        from_status="To Do",
        to_status="In Progress",
        to_status_category=StatusCategory.IN_PROGRESS,
        occurred_at=NOW - timedelta(days=8),
    )
    t2 = Transition(
        entity_type=EntityType.WORKITEM,
        entity_id=added.id,
        from_status="To Do",
        to_status="In Progress",
        to_status_category=StatusCategory.IN_PROGRESS,
        occurred_at=NOW - timedelta(days=2),
    )
    return (
        SignalData(
            report_id=uuid4(),
            projects=(_project(),),
            boards=(_board(),),
            sprints=(s,),
            workitems=(original, added),
            transitions=(t1, t2),
        ),
        _ctx(sprint_id=s.id),
        JiraConnector.describe_signal_schema(),
        [_board_scope()],
        {"original_count", "added_count", "churn_pct"},
    )


def _mr_waiting_fixture():
    mr = _mr(1)
    review = Review(
        mergerequest_id=mr.id,
        reviewer_id=uuid4(),
        decision=ReviewDecision.APPROVED,
        submitted_at=NOW - timedelta(days=5),
    )
    return (
        SignalData(report_id=uuid4(), mergerequests=(mr,), reviews=(review,)),
        _ctx(),
        GitLabConnector.describe_signal_schema(),
        [_mr_scope(("reviews",))],
        {"state", "age_since_last_review_activity"},
    )


def _mr_no_link_fixture():
    mr = _mr(1, linked_workitem_keys=[])
    return (
        SignalData(report_id=uuid4(), mergerequests=(mr,)),
        _ctx(),
        GitLabConnector.describe_signal_schema(),
        [_mr_scope()],
        {"state", "linked_workitem_keys"},
    )


def _large_mr_fixture():
    mr = _mr(1, changed_files_count=25)
    return (
        SignalData(report_id=uuid4(), mergerequests=(mr,)),
        _ctx(),
        GitLabConnector.describe_signal_schema(),
        [_mr_scope()],
        {"changed_files_count"},
    )


def _failing_pipeline_fixture():
    mr = _mr(1, pipeline_status=PipelineStatus.FAILED, pipeline_updated_at=NOW - timedelta(days=2))
    return (
        SignalData(report_id=uuid4(), mergerequests=(mr,)),
        _ctx(),
        GitLabConnector.describe_signal_schema(),
        [_mr_scope(("pipelines",))],
        {"pipeline_status", "age_since_pipeline_update"},
    )


def _merged_no_approval_fixture():
    mr = _mr(1, state=MergeRequestState.MERGED, approval_count=0)
    return (
        SignalData(report_id=uuid4(), mergerequests=(mr,)),
        _ctx(),
        GitLabConnector.describe_signal_schema(),
        [_mr_scope(("reviews",))],
        {"state", "approval_count"},
    )


# ---------------------------------------------------------------------------
# Parametrized conformance suite
# ---------------------------------------------------------------------------


SIGNAL_FIXTURES = [
    ("stale-in-progress-work-item", _stale_fixture),
    ("blocked-without-update", _blocked_fixture),
    ("story-without-acceptance-criteria", _no_ac_fixture),
    ("story-without-parent-epic", _no_epic_fixture),
    ("epic-too-broad", _epic_too_broad_fixture),
    ("epic-without-measurable-description", _epic_no_description_fixture),
    ("repeated-carry-over", _carry_over_fixture),
    ("sprint-scope-churn", _churn_fixture),
    ("mergerequest-waiting-too-long", _mr_waiting_fixture),
    ("mergerequest-without-linked-workitem", _mr_no_link_fixture),
    ("large-mergerequest-risk", _large_mr_fixture),
    ("failing-pipeline-too-long", _failing_pipeline_fixture),
    ("merged-without-enough-approval", _merged_no_approval_fixture),
]


@pytest.mark.parametrize(
    "template_key,fixture_fn",
    SIGNAL_FIXTURES,
    ids=[t[0] for t in SIGNAL_FIXTURES],
)
def test_signal_evidence_contains_expression_fields(template_key: str, fixture_fn: object) -> None:
    """Each signal's evidence must contain exactly the fields its expression references.

    WI/sprint signals also include scope_id; MR signals do not (no per-scope iteration).
    The exact key set is stable: no extra or missing keys from the generic builder.
    """
    data, ctx, schema, scopes, expected_keys = fixture_fn()  # type: ignore[call-arg]
    definition = _defn(template_key)

    findings = evaluate_signal_definition(definition, data, ctx, schema, scopes)

    assert len(findings) >= 1, f"{template_key}: expected at least one finding from the fixture"
    ev = findings[0].evidence
    # WI and sprint signals include scope_id; MR signals do not
    wi_or_sprint = definition.entity_type in ("issue", "sprint")
    expected_exact = (expected_keys | {"scope_id"}) if wi_or_sprint else expected_keys
    missing = expected_exact - set(ev)
    assert not missing, f"{template_key}: evidence missing keys {missing}. Got: {set(ev)}"
    extra = set(ev) - expected_exact
    assert not extra, (
        f"{template_key}: evidence has unexpected keys {extra}. Expected: {expected_exact}"
    )


@pytest.mark.parametrize(
    "template_key,fixture_fn", SIGNAL_FIXTURES, ids=[t[0] for t in SIGNAL_FIXTURES]
)
def test_signal_confidence_is_high(template_key: str, fixture_fn: object) -> None:
    """All deterministic signals must emit HIGH confidence (data model §6.6)."""
    data, ctx, schema, scopes, _ = fixture_fn()
    definition = _defn(template_key)

    findings = evaluate_signal_definition(definition, data, ctx, schema, scopes)

    assert len(findings) >= 1, f"{template_key}: no findings"
    for finding in findings:
        assert finding.confidence is Confidence.HIGH, (
            f"{template_key}: expected HIGH confidence, got {finding.confidence}"
        )


def test_no_template_key_evidence_branches_in_declarative_engine() -> None:
    """Confirm the declarative evaluator has no template_key == branches for evidence."""
    import re
    from pathlib import Path

    declarative_py = (
        Path(__file__).parents[3]
        / "packages"
        / "core"
        / "src"
        / "em_radar_core"
        / "evaluation"
        / "declarative.py"
    )
    source = declarative_py.read_text(encoding="utf-8")
    matches = re.findall(
        r"template_key\s*(?:==|!=|not\s+in\b|\bin\b|\.get\()",
        source,
    )
    assert matches == [], f"Found template_key dispatch branches in declarative.py: {matches}"
