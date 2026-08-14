"""Verification tests for M5-11: de-hardcoded evaluator with generic evidence.

Asserts that:
1. All eight work-item signals fire with expression-derived evidence (no template_key lookup).
2. Sprint-scope-churn fires via a pure sprint-entity expression with generic evidence.
3. declarative.py contains no `template_key ==` evaluation/evidence branch.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4


from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import (
    EntityType,
    StatusCategory,
    WorkItemType,
)
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector
from em_radar_config import instantiate_jira_signal_template

from _signal_helpers import NOW, board, context, project, sprint, workitem, transition

_DECLARATIVE_PY = (
    Path(__file__).parents[3]
    / "packages"
    / "core"
    / "src"
    / "em_radar_core"
    / "evaluation"
    / "declarative.py"
)


def _scope(scope_type: str = "project", capabilities: tuple[str, ...] = ()) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type=scope_type,
        name="Radar",
        external_ref={"id": "BOARD" if scope_type == "board" else "PROJECT", "key": "RAD"},
        capabilities=("statuses", "labels", *capabilities),
    )


def _sprint_scope() -> ScopeDescriptor:
    return _scope("board", ("sprint",))


# ---------------------------------------------------------------------------
# 1. Work-item signals fire with generic (expression-derived) evidence
# ---------------------------------------------------------------------------


def test_stale_in_progress_fires_with_generic_evidence() -> None:
    item = workitem(updated_at=NOW - timedelta(days=10))
    ctx = context()
    data = SignalData(
        report_id=uuid4(),
        projects=(project(),),
        workitems=(item,),
        transitions=(
            transition(
                item.id,
                occurred_at=NOW - timedelta(days=9),
                to_status_category=StatusCategory.IN_PROGRESS,
            ),
        ),
    )
    definition = instantiate_jira_signal_template("stale-in-progress-work-item")

    findings = evaluate_signal_definition(
        definition, data, ctx, JiraConnector.describe_signal_schema(), [_scope()]
    )

    assert len(findings) == 1
    ev = findings[0].evidence
    assert "age_in_current_status" in ev, f"expected age_in_current_status in evidence, got {ev}"
    assert "status_category" in ev


def test_blocked_without_update_fires_with_generic_evidence() -> None:
    item = workitem(
        status="Blocked",
        status_category=StatusCategory.BLOCKED,
        is_blocked=True,
        updated_at=NOW - timedelta(days=5),
    )
    data = SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,))
    definition = instantiate_jira_signal_template("blocked-without-update")

    findings = evaluate_signal_definition(
        definition, data, context(), JiraConnector.describe_signal_schema(), [_scope()]
    )

    assert len(findings) == 1
    ev = findings[0].evidence
    assert "age_since_updated" in ev


def test_story_without_acceptance_criteria_fires_with_generic_evidence() -> None:
    item = workitem(item_type=WorkItemType.STORY, acceptance_criteria=None)
    data = SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,))
    definition = instantiate_jira_signal_template("story-without-acceptance-criteria")

    findings = evaluate_signal_definition(
        definition, data, context(), JiraConnector.describe_signal_schema(), [_scope()]
    )

    assert len(findings) == 1
    ev = findings[0].evidence
    assert "acceptance_criteria" in ev
    assert "issue_type" in ev


def test_story_without_parent_epic_fires_with_generic_evidence() -> None:
    item = workitem(item_type=WorkItemType.STORY, parent_id=None)
    data = SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,))
    definition = instantiate_jira_signal_template("story-without-parent-epic")

    findings = evaluate_signal_definition(
        definition, data, context(), JiraConnector.describe_signal_schema(), [_scope()]
    )

    assert len(findings) == 1
    ev = findings[0].evidence
    assert "parent_id" in ev


def test_epic_too_broad_fires_with_generic_evidence() -> None:

    epic = workitem(key="EPIC-1", item_type=WorkItemType.EPIC)
    children = [workitem(key=f"CHILD-{i}", parent_id=epic.id) for i in range(16)]
    all_items = (epic, *children)
    data = SignalData(report_id=uuid4(), projects=(project(),), workitems=all_items)
    definition = instantiate_jira_signal_template("epic-too-broad")

    findings = evaluate_signal_definition(
        definition, data, context(), JiraConnector.describe_signal_schema(), [_scope()]
    )

    assert len(findings) == 1
    ev = findings[0].evidence
    assert "child_count" in ev
    assert ev["child_count"] == 16


def test_epic_without_measurable_description_fires_with_generic_evidence() -> None:
    epic = workitem(key="EPIC-1", item_type=WorkItemType.EPIC, description="Short")
    data = SignalData(report_id=uuid4(), projects=(project(),), workitems=(epic,))
    definition = instantiate_jira_signal_template("epic-without-measurable-description")

    findings = evaluate_signal_definition(
        definition, data, context(), JiraConnector.describe_signal_schema(), [_scope()]
    )

    assert len(findings) == 1
    ev = findings[0].evidence
    assert "description_length" in ev


def test_repeated_carry_over_fires_with_generic_evidence() -> None:
    sprint1_id = uuid4()
    sprint2_id = uuid4()
    item = workitem(
        sprint_ids=[sprint1_id, sprint2_id],
        current_sprint_id=sprint2_id,
        status="In Progress",
        status_category=StatusCategory.IN_PROGRESS,
    )
    s1 = sprint(name="Sprint 1")
    s1.id = sprint1_id
    s2 = sprint(name="Sprint 2")
    s2.id = sprint2_id
    data = SignalData(
        report_id=uuid4(),
        projects=(project(),),
        boards=(board(),),
        sprints=(s1, s2),
        workitems=(item,),
    )
    ctx = context(sprint_id=sprint2_id)
    definition = instantiate_jira_signal_template("repeated-carry-over")

    findings = evaluate_signal_definition(
        definition, data, ctx, JiraConnector.describe_signal_schema(), [_sprint_scope()]
    )

    assert len(findings) == 1
    ev = findings[0].evidence
    assert "sprint_count" in ev
    assert ev["sprint_count"] == 2


# ---------------------------------------------------------------------------
# 2. Sprint-scope-churn fires via pure sprint-entity expression
# ---------------------------------------------------------------------------


def test_sprint_scope_churn_fires_via_sprint_entity_expression() -> None:
    """sprint-scope-churn now evaluates as entity_type=sprint, no template_key lookup."""

    s = sprint(name="Sprint 1", start_date=NOW - timedelta(days=7))
    original = workitem(key="RAD-1", sprint_ids=[s.id], current_sprint_id=s.id)
    added = workitem(key="RAD-2", sprint_ids=[s.id], current_sprint_id=s.id)
    t_original = transition(
        original.id,
        occurred_at=NOW - timedelta(days=8),
        to_status_category=StatusCategory.IN_PROGRESS,
    )
    t_added = transition(
        added.id, occurred_at=NOW - timedelta(days=2), to_status_category=StatusCategory.IN_PROGRESS
    )
    data = SignalData(
        report_id=uuid4(),
        projects=(project(),),
        boards=(board(),),
        sprints=(s,),
        workitems=(original, added),
        transitions=(t_original, t_added),
    )
    ctx = context(sprint_id=s.id)
    definition = instantiate_jira_signal_template("sprint-scope-churn")

    findings = evaluate_signal_definition(
        definition, data, ctx, JiraConnector.describe_signal_schema(), [_sprint_scope()]
    )

    assert len(findings) == 1
    assert findings[0].entity_type is EntityType.SPRINT
    ev = findings[0].evidence
    assert ev["sprint_scope_added_pct"] == 100.0
    # Fixture: 1 original (transition 8 days ago, before sprint start 7 days ago),
    # 1 added (transition 2 days ago, after sprint start).
    assert ev["original_count"] == 1
    assert ev["added_count"] == 1


def test_sprint_scope_churn_multi_transition_item_counted_once() -> None:
    """An original item with multiple pre-start transitions is counted once, not N times."""
    s = sprint(name="Sprint 1", start_date=NOW - timedelta(days=7))
    original = workitem(key="RAD-1", sprint_ids=[s.id], current_sprint_id=s.id)
    t1 = transition(
        original.id,
        occurred_at=NOW - timedelta(days=10),
        to_status_category=StatusCategory.IN_PROGRESS,
    )
    t2 = transition(
        original.id,
        occurred_at=NOW - timedelta(days=9),
        to_status_category=StatusCategory.IN_PROGRESS,
    )
    t3 = transition(
        original.id,
        occurred_at=NOW - timedelta(days=8),
        to_status_category=StatusCategory.IN_PROGRESS,
    )
    # No added items → original=1, added=0, churn=0% → signal should NOT fire (threshold=20%)
    data = SignalData(
        report_id=uuid4(),
        projects=(project(),),
        boards=(board(),),
        sprints=(s,),
        workitems=(original,),
        transitions=(t1, t2, t3),
    )
    ctx = context(sprint_id=s.id)
    definition = instantiate_jira_signal_template("sprint-scope-churn")

    findings = evaluate_signal_definition(
        definition, data, ctx, JiraConnector.describe_signal_schema(), [_sprint_scope()]
    )

    assert findings == [], (
        "No churn when all items were in sprint at start; "
        "multi-transition original item must not be double-counted"
    )


def test_sprint_scope_churn_below_threshold_does_not_fire() -> None:
    """Churn below the 20% threshold must produce no findings."""
    s = sprint(name="Sprint 1", start_date=NOW - timedelta(days=7))
    # 10 original, 1 added → 10% churn < 20%
    originals = [
        workitem(key=f"RAD-{i}", sprint_ids=[s.id], current_sprint_id=s.id) for i in range(10)
    ]
    added_item = workitem(key="RAD-NEW", sprint_ids=[s.id], current_sprint_id=s.id)
    transitions = tuple(
        transition(
            wi.id,
            occurred_at=NOW - timedelta(days=8),
            to_status_category=StatusCategory.IN_PROGRESS,
        )
        for wi in originals
    )
    data = SignalData(
        report_id=uuid4(),
        projects=(project(),),
        boards=(board(),),
        sprints=(s,),
        workitems=tuple([*originals, added_item]),
        transitions=transitions,
    )
    ctx = context(sprint_id=s.id)
    definition = instantiate_jira_signal_template("sprint-scope-churn")

    findings = evaluate_signal_definition(
        definition, data, ctx, JiraConnector.describe_signal_schema(), [_sprint_scope()]
    )

    assert findings == []


def test_sprint_scope_churn_evidence_counts_with_multiple_originals() -> None:
    """Evidence counts are correct when original_count > 1, proving they are not always 1/1."""
    s = sprint(name="Sprint 1", start_date=NOW - timedelta(days=7))
    # 3 originals (transition before sprint start), 2 added (transition after sprint start)
    originals = [
        workitem(key=f"RAD-{i}", sprint_ids=[s.id], current_sprint_id=s.id) for i in range(3)
    ]
    added_items = [
        workitem(key=f"RAD-NEW-{i}", sprint_ids=[s.id], current_sprint_id=s.id) for i in range(2)
    ]
    original_transitions = tuple(
        transition(
            wi.id,
            occurred_at=NOW - timedelta(days=8),
            to_status_category=StatusCategory.IN_PROGRESS,
        )
        for wi in originals
    )
    added_transitions = tuple(
        transition(
            wi.id,
            occurred_at=NOW - timedelta(days=2),
            to_status_category=StatusCategory.IN_PROGRESS,
        )
        for wi in added_items
    )
    data = SignalData(
        report_id=uuid4(),
        projects=(project(),),
        boards=(board(),),
        sprints=(s,),
        workitems=tuple([*originals, *added_items]),
        transitions=original_transitions + added_transitions,
    )
    ctx = context(sprint_id=s.id)
    definition = instantiate_jira_signal_template("sprint-scope-churn")

    findings = evaluate_signal_definition(
        definition, data, ctx, JiraConnector.describe_signal_schema(), [_sprint_scope()]
    )

    # 2/3 = 66.67% churn — above the 20% threshold, must fire
    assert len(findings) == 1
    ev = findings[0].evidence
    assert ev["original_count"] == 3
    assert ev["added_count"] == 2
    assert ev["sprint_scope_added_pct"] == round(2 / 3 * 100.0, 2)


# ---------------------------------------------------------------------------
# 3. No template_key == branch in declarative.py
# ---------------------------------------------------------------------------


def test_declarative_py_has_no_template_key_equality_branches() -> None:
    """After M5-11, declarative.py must not branch on template_key for evaluation or evidence."""
    source = _DECLARATIVE_PY.read_text()
    # Matches 'template_key ==' or '== "template-name"' patterns (evaluation/evidence branching)
    matches = re.findall(r"template_key\s*==", source)
    assert matches == [], f"declarative.py still contains template_key == branches: {matches}"
