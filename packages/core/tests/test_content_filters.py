"""Tests for content filter fields: workitem_types, labels, exclude_labels, branches."""

from uuid import uuid4

from em_radar_core.connectors import (
    SignalCapabilitySchema,
    SignalField,
    SignalScopeType,
)
from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin, WorkItemType
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, context, project, workitem


def _definition(expression: dict[str, object]) -> SignalDefinition:
    return SignalDefinition(
        name="Content filter test",
        entity_type="issue",
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Radar",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "RAD", "name": "Radar"},
        capabilities=("statuses", "labels"),
    )


def _branches_schema() -> SignalCapabilitySchema:
    """Minimal schema used to test the branches filter and matches_glob operator."""
    return SignalCapabilitySchema(
        connector_type="test",
        entity_types=("issue",),
        scope_types=(SignalScopeType("project", "Project"),),
        fields=(
            SignalField(
                "status_category",
                "Status Category",
                "enum",
                ("is", "is_not"),
                values=("todo", "in_progress", "done", "blocked"),
            ),
            SignalField(
                "branches",
                "Branches",
                "string",
                ("matches_glob", "is"),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# workitem_types filter
# ---------------------------------------------------------------------------


def test_workitem_types_narrows_by_type() -> None:
    story = workitem(key="RAD-1", item_type=WorkItemType.STORY)
    bug = workitem(key="RAD-2", item_type=WorkItemType.BUG)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "workitem_types", "operator": "is_any_of", "value": ["story"]},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(story, bug)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]


def test_workitem_types_absent_evaluates_all() -> None:
    story = workitem(key="RAD-1", item_type=WorkItemType.STORY)
    bug = workitem(key="RAD-2", item_type=WorkItemType.BUG)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "status_category", "operator": "is", "value": "in_progress"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(story, bug)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 2


def test_workitem_types_is_none_of_excludes_matching_type() -> None:
    story = workitem(key="RAD-1", item_type=WorkItemType.STORY)
    bug = workitem(key="RAD-2", item_type=WorkItemType.BUG)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "workitem_types", "operator": "is_none_of", "value": ["bug"]},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(story, bug)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]


# ---------------------------------------------------------------------------
# labels filter
# ---------------------------------------------------------------------------


def test_labels_filter_narrows_to_matching_items() -> None:
    tagged = workitem(key="RAD-1", labels=["urgent"])
    untagged = workitem(key="RAD-2", labels=[])
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "labels", "operator": "contains", "value": "urgent"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(tagged, untagged)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]


def test_labels_absent_evaluates_all() -> None:
    tagged = workitem(key="RAD-1", labels=["urgent"])
    untagged = workitem(key="RAD-2", labels=[])
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "status_category", "operator": "is", "value": "in_progress"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(tagged, untagged)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 2


# ---------------------------------------------------------------------------
# exclude_labels filter
# ---------------------------------------------------------------------------


def test_exclude_labels_removes_matching_items() -> None:
    keep = workitem(key="RAD-1", labels=[])
    skip = workitem(key="RAD-2", labels=["wont-fix"])
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "exclude_labels", "operator": "does_not_contain", "value": "wont-fix"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(keep, skip)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]


def test_exclude_labels_does_not_contain_any_removes_any_match() -> None:
    clean = workitem(key="RAD-1", labels=["active"])
    archived = workitem(key="RAD-2", labels=["archived"])
    excluded = workitem(key="RAD-3", labels=["wont-fix"])
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {
                "field": "exclude_labels",
                "operator": "does_not_contain_any",
                "value": ["wont-fix", "archived"],
            },
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(clean, archived, excluded)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]


def test_exclude_labels_absent_evaluates_all() -> None:
    with_label = workitem(key="RAD-1", labels=["wont-fix"])
    without_label = workitem(key="RAD-2", labels=[])
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "status_category", "operator": "is", "value": "in_progress"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(with_label, without_label)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 2


# ---------------------------------------------------------------------------
# branches filter (glob matching)
# ---------------------------------------------------------------------------


def test_branches_filter_returns_no_findings_for_workitems() -> None:
    """Work items have no branch attribute; a branches condition filters them all out."""
    item = workitem(key="RAD-1")
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "branches", "operator": "matches_glob", "value": "feature/*"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        _branches_schema(),
        [_scope()],
    )

    assert findings == []


def test_branches_absent_evaluates_all_workitems() -> None:
    item = workitem(key="RAD-1")
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "status_category", "operator": "is", "value": "in_progress"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        _branches_schema(),
        [_scope()],
    )

    assert len(findings) == 1


def test_matches_glob_operator_accepts_wildcard_pattern() -> None:
    """Glob patterns using * and ? are matched via fnmatch (case-sensitive)."""
    from em_radar_core.evaluation.declarative import _compare

    assert _compare("feature/my-branch", "matches_glob", "feature/*") is True
    assert _compare("main", "matches_glob", "feature/*") is False
    assert _compare("release/1.0", "matches_glob", "release/?.*") is True
    assert _compare(None, "matches_glob", "feature/*") is False
    # Matching is case-sensitive for determinism across platforms.
    assert _compare("Feature/x", "matches_glob", "feature/*") is False


# ---------------------------------------------------------------------------
# workitem_types is / is_not operators
# ---------------------------------------------------------------------------


def test_workitem_types_is_matches_exact_type() -> None:
    story = workitem(key="RAD-1", item_type=WorkItemType.STORY)
    bug = workitem(key="RAD-2", item_type=WorkItemType.BUG)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "workitem_types", "operator": "is", "value": "story"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(story, bug)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]


def test_workitem_types_is_not_excludes_exact_type() -> None:
    story = workitem(key="RAD-1", item_type=WorkItemType.STORY)
    bug = workitem(key="RAD-2", item_type=WorkItemType.BUG)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "workitem_types", "operator": "is_not", "value": "bug"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(story, bug)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]


# ---------------------------------------------------------------------------
# Composition: content filter combined with a domain condition
# ---------------------------------------------------------------------------


def test_workitem_types_filter_composes_with_domain_condition() -> None:
    """Content filter and non-filter conditions must both be satisfied within a group."""
    in_progress_story = workitem(key="RAD-1", item_type=WorkItemType.STORY)
    in_progress_bug = workitem(key="RAD-2", item_type=WorkItemType.BUG)
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "workitem_types", "operator": "is_any_of", "value": ["story"]},
            {"field": "status_category", "operator": "is", "value": "in_progress"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(
            report_id=uuid4(), projects=(project(),), workitems=(in_progress_story, in_progress_bug)
        ),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]


def test_exclude_labels_composes_with_domain_condition() -> None:
    """exclude_labels filter combined with a status condition narrows both simultaneously."""
    keep = workitem(key="RAD-1", labels=[])
    skip_label = workitem(key="RAD-2", labels=["wont-fix"])
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "status_category", "operator": "is", "value": "in_progress"},
            {"field": "exclude_labels", "operator": "does_not_contain", "value": "wont-fix"},
        ],
    }

    findings = evaluate_signal_definition(
        _definition(expression),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(keep, skip_label)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert [f.title for f in findings] == ["RAD-1 - RAD-1 title"]
