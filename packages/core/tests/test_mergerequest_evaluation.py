"""Tests for merge-request entity evaluation in the declarative evaluator (M5-10).

Verifies that signals with entity_type='merge_request' iterate MergeRequest entities,
that MR-specific fields resolve correctly, and that the expression validator accepts
MR schema fields and rejects workitem-only fields for MR signals.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from em_radar_core.evaluation import (
    ExpressionValidationError,
    ScopeDescriptor,
    evaluate_signal_definition,
    validate_expression,
)
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
from em_radar_connector_gitlab.connector import GitLabConnector
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, context, project

_REPO_ID = uuid4()
_AUTHOR_ID = uuid4()


def _mr_definition(expression: dict[str, object]) -> SignalDefinition:
    return SignalDefinition(
        name="MR test signal",
        entity_type="merge_request",
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="gitlab-1",
        scope_id="scope-1",
        scope_type="repository",
        name="My repo",
        external_ref={"id": "repo-1"},
        capabilities=("reviews",),
    )


def _mr(
    iid: int = 1,
    *,
    state: MergeRequestState = MergeRequestState.OPEN,
    is_draft: bool = False,
    source_branch: str = "feature/my-branch",
    target_branch: str = "main",
    approval_count: int = 0,
    changed_files_count: int | None = None,
    pipeline_status: PipelineStatus | None = None,
    pipeline_updated_at=None,
    linked_workitem_keys: list[str] | None = None,
    additions: int | None = None,
    deletions: int | None = None,
    created_at=None,
    updated_at=None,
    merged_at=None,
    closed_at=None,
) -> MergeRequest:
    state_val = state
    if state is MergeRequestState.MERGED and merged_at is None:
        merged_at = NOW
    if state is MergeRequestState.CLOSED and closed_at is None:
        closed_at = NOW
    return MergeRequest(
        source=Source.GITLAB,
        external_id=f"mr-{iid}",
        repository_id=_REPO_ID,
        iid=iid,
        title=f"MR {iid}",
        state=state_val,
        is_draft=is_draft,
        author_id=_AUTHOR_ID,
        source_branch=source_branch,
        target_branch=target_branch,
        approval_count=approval_count,
        changed_files_count=changed_files_count,
        pipeline_status=pipeline_status,
        pipeline_updated_at=pipeline_updated_at,
        linked_workitem_keys=linked_workitem_keys or [],
        additions=additions,
        deletions=deletions,
        created_at=created_at or NOW,
        updated_at=updated_at or NOW,
        merged_at=merged_at,
        closed_at=closed_at,
    )


def _data(*mrs: MergeRequest, reviews: tuple[Review, ...] = ()) -> SignalData:
    return SignalData(
        report_id=uuid4(),
        projects=(project(),),
        mergerequests=tuple(mrs),
        reviews=reviews,
    )


# ---------------------------------------------------------------------------
# State and basic field evaluation
# ---------------------------------------------------------------------------


def test_mr_state_is_fires_on_opened() -> None:
    open_mr = _mr(1, state=MergeRequestState.OPEN)
    merged_mr = _mr(2, state=MergeRequestState.MERGED)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "state", "operator": "is", "value": "open"}],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(open_mr, merged_mr),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == open_mr.id
    assert findings[0].title == "!1 - MR 1"


def test_mr_is_draft_filter() -> None:
    draft = _mr(1, is_draft=True)
    ready = _mr(2, is_draft=False)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "is_draft", "operator": "is", "value": False}],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(draft, ready),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == ready.id


def test_mr_approval_count_threshold() -> None:
    approved = _mr(1, approval_count=2)
    unapproved = _mr(2, approval_count=0)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "approval_count", "operator": "greater_than", "value": 1}],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(approved, unapproved),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == approved.id


def test_mr_changed_files_count_threshold() -> None:
    large = _mr(1, changed_files_count=25)
    small = _mr(2, changed_files_count=5)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "changed_files_count", "operator": "greater_than", "value": 20}],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(large, small),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == large.id


# ---------------------------------------------------------------------------
# Age field evaluation
# ---------------------------------------------------------------------------


def test_mr_age_since_created() -> None:
    old = _mr(1, created_at=NOW - timedelta(days=5), updated_at=NOW - timedelta(days=5))
    new = _mr(2, created_at=NOW - timedelta(days=1), updated_at=NOW - timedelta(days=1))
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {
                "field": "age_since_created",
                "operator": "greater_than",
                "value": {"amount": 3, "unit": "days"},
            }
        ],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(old, new),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == old.id


def test_mr_age_since_last_review_activity() -> None:
    mr1 = _mr(1)
    mr2 = _mr(2)
    old_review = Review(
        mergerequest_id=mr1.id,
        reviewer_id=uuid4(),
        decision=ReviewDecision.APPROVED,
        submitted_at=NOW - timedelta(days=5),
    )
    recent_review = Review(
        mergerequest_id=mr2.id,
        reviewer_id=uuid4(),
        decision=ReviewDecision.APPROVED,
        submitted_at=NOW - timedelta(days=1),
    )
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {
                "field": "age_since_last_review_activity",
                "operator": "greater_than",
                "value": {"amount": 3, "unit": "days"},
            }
        ],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(mr1, mr2, reviews=(old_review, recent_review)),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == mr1.id


def test_mr_no_review_returns_no_match_for_age_since_last_review() -> None:
    """An MR with no reviews has None age_since_last_review_activity → no match."""
    mr = _mr(1)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {
                "field": "age_since_last_review_activity",
                "operator": "greater_than",
                "value": {"amount": 0, "unit": "days"},
            }
        ],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(mr, reviews=()),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert findings == []


# ---------------------------------------------------------------------------
# Compound expression: state AND age
# ---------------------------------------------------------------------------


def test_mr_compound_state_and_age_since_created() -> None:
    """state is opened AND age_since_created > 3 days."""
    matches = _mr(
        1,
        state=MergeRequestState.OPEN,
        created_at=NOW - timedelta(days=5),
        updated_at=NOW - timedelta(days=5),
    )
    too_new = _mr(
        2,
        state=MergeRequestState.OPEN,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    already_merged = _mr(
        3,
        state=MergeRequestState.MERGED,
        created_at=NOW - timedelta(days=5),
        updated_at=NOW - timedelta(days=5),
    )
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "state", "operator": "is", "value": "open"},
            {
                "field": "age_since_created",
                "operator": "greater_than",
                "value": {"amount": 3, "unit": "days"},
            },
        ],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(matches, too_new, already_merged),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == matches.id


# ---------------------------------------------------------------------------
# Pipeline status evaluation
# ---------------------------------------------------------------------------


def test_mr_pipeline_status_failed() -> None:
    failing = _mr(1, pipeline_status=PipelineStatus.FAILED)
    passing = _mr(2, pipeline_status=PipelineStatus.SUCCESS)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "pipeline_status", "operator": "is", "value": "failed"}],
    }
    pipeline_scope = ScopeDescriptor(
        connector_id="gitlab-1",
        scope_id="scope-1",
        scope_type="repository",
        name="My repo",
        external_ref={"id": "repo-1"},
        capabilities=("reviews", "pipelines"),
    )

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(failing, passing),
        context(),
        GitLabConnector.describe_signal_schema(),
        [pipeline_scope],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == failing.id


# ---------------------------------------------------------------------------
# Linked work items
# ---------------------------------------------------------------------------


def test_mr_linked_workitem_keys_is_empty() -> None:
    unlinked = _mr(1, linked_workitem_keys=[])
    linked = _mr(2, linked_workitem_keys=["PLAT-42"])
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "linked_workitem_keys", "operator": "is_empty"}],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(unlinked, linked),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == unlinked.id


# ---------------------------------------------------------------------------
# Branch content filter (M5-01 reuse for MR)
# ---------------------------------------------------------------------------


def test_mr_source_branch_glob_filter() -> None:
    feature = _mr(1, source_branch="feature/my-branch")
    main_branch = _mr(2, source_branch="main")
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "source_branch", "operator": "is", "value": "feature/my-branch"}],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(feature, main_branch),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == feature.id


# ---------------------------------------------------------------------------
# validate_expression rejects workitem-only fields for MR signals
# ---------------------------------------------------------------------------


def test_validate_expression_rejects_workitem_field_in_mr_signal() -> None:
    """status_category is a Jira/workitem field; it should not be valid in an MR expression."""
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "status_category", "operator": "is", "value": "in_progress"}],
    }

    with pytest.raises(ExpressionValidationError, match="unknown field"):
        validate_expression(expression, GitLabConnector.describe_signal_schema(), [_scope()])


def test_validate_expression_accepts_mr_field() -> None:
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "state", "operator": "is", "value": "open"}],
    }

    # Should not raise
    validate_expression(expression, GitLabConnector.describe_signal_schema(), [_scope()])


def test_validate_expression_rejects_mr_field_in_jira_signal() -> None:
    """state is a GitLab MR field; it should not be valid in a Jira expression."""
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "state", "operator": "is", "value": "open"}],
    }

    with pytest.raises(ExpressionValidationError, match="unknown field"):
        validate_expression(expression, JiraConnector.describe_signal_schema(), [_scope()])


# ---------------------------------------------------------------------------
# closed_at field (bug fix: was missing, would crash at evaluation time)
# ---------------------------------------------------------------------------


def test_mr_closed_at_field_is_supported() -> None:
    """closed_at is a schema-valid GitLab field; evaluating it must not raise."""
    closed = _mr(1, state=MergeRequestState.CLOSED, updated_at=NOW - timedelta(days=2))
    open_mr = _mr(2)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "closed_at", "operator": "before", "value": NOW.isoformat()}],
    }

    # closed MR has closed_at = NOW (set by _mr helper); NOW is not before NOW → no match.
    # open MR has closed_at = None → _compare returns False for datetime ops on None.
    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(closed, open_mr),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    # Both are non-matches (closed MR's closed_at == NOW, not strictly before NOW;
    # open MR has no closed_at). Key assertion: no ExpressionValidationError is raised.
    assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# title contains (substring matching, not list membership)
# ---------------------------------------------------------------------------


def test_mr_title_contains_substring() -> None:
    wip = _mr(1)
    wip.title = "WIP: refactor auth"
    ready = _mr(2)
    ready.title = "Add login form"
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "title", "operator": "contains", "value": "WIP"}],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(wip, ready),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == wip.id


def test_mr_title_does_not_contain_substring() -> None:
    wip = _mr(1)
    wip.title = "WIP: refactor auth"
    ready = _mr(2)
    ready.title = "Add login form"
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "title", "operator": "does_not_contain", "value": "WIP"}],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(wip, ready),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == ready.id


# ---------------------------------------------------------------------------
# age_since_updated (additional schema field coverage)
# ---------------------------------------------------------------------------


def test_mr_age_since_updated() -> None:
    stale = _mr(1, created_at=NOW - timedelta(days=10), updated_at=NOW - timedelta(days=5))
    fresh = _mr(2, created_at=NOW - timedelta(days=10), updated_at=NOW - timedelta(days=1))
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {
                "field": "age_since_updated",
                "operator": "greater_than",
                "value": {"amount": 3, "unit": "days"},
            }
        ],
    }

    findings = evaluate_signal_definition(
        _mr_definition(expression),
        _data(stale, fresh),
        context(),
        GitLabConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].entity_id == stale.id
