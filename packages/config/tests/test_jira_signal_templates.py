from datetime import UTC, datetime, timedelta
from uuid import uuid4

from em_radar_config import (
    JIRA_SIGNAL_TEMPLATES,
    instantiate_jira_signal_template,
    restore_jira_signal_template,
    seed_jira_signal_templates,
)
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import (
    Board,
    BoardType,
    EntityType,
    EvaluationContext,
    EvaluationWindow,
    Project,
    SignalOrigin,
    Source,
    Sprint,
    SprintState,
    StatusCategory,
    TeamProfile,
    Transition,
    WindowType,
    WorkItem,
    WorkItemType,
)
from em_radar_core.signals import SignalData

NOW = datetime(2026, 1, 20, 12, tzinfo=UTC)
PROJECT_ID = uuid4()
BOARD_ID = uuid4()


def test_templates_seed_once() -> None:
    first = seed_jira_signal_templates()
    second = seed_jira_signal_templates()

    assert first == second
    assert len(first) == 8


def test_template_duplicates_into_runnable_definition() -> None:
    definition = instantiate_jira_signal_template("stale-in-progress-work-item")

    assert definition.enabled is True
    assert definition.origin is SignalOrigin.SYSTEM_TEMPLATE
    assert definition.template_key == "stale-in-progress-work-item"


def test_restore_built_in_defaults_without_deleting_user_copies() -> None:
    copied = instantiate_jira_signal_template(
        "blocked-without-update",
        name="Team-specific blocked work",
    )
    restored = restore_jira_signal_template("blocked-without-update")

    assert copied.name == "Team-specific blocked work"
    assert restored.name == "Blocked without update"


def test_m2_m3_parameter_overrides_have_equivalent_expression_values() -> None:
    stale = restore_jira_signal_template("stale-in-progress-work-item")
    age_condition = stale.expression["conditions"][1]

    assert age_condition["field"] == "age_in_current_status"
    assert age_condition["value"] == {"amount": 7, "unit": "days"}


def test_all_eight_jira_templates_preserve_evidence_contracts() -> None:
    expected = {
        "stale-in-progress-work-item": ("days_idle", "last_updated_at", "threshold"),
        "blocked-without-update": ("days_blocked_idle", "last_updated_at", "threshold"),
        "story-without-acceptance-criteria": ("workitem_type", "has_description"),
        "story-without-parent-epic": ("workitem_type",),
        "epic-too-broad": ("child_count", "threshold"),
        "epic-without-measurable-description": ("description_length", "threshold"),
        "repeated-carry-over": ("sprint_count", "sprint_names"),
        "sprint-scope-churn": ("original_count", "added_count", "churn_pct"),
    }

    assert {template.key: template.evidence_shape for template in JIRA_SIGNAL_TEMPLATES} == expected


def test_jira_template_expressions_match_positive_and_negative_fixtures() -> None:
    epic = _workitem("RAD-1", item_type=WorkItemType.EPIC, description="short")
    stories = [_workitem(f"RAD-{index}", parent_id=epic.id) for index in range(2, 18)]
    no_ac = _workitem("RAD-18", acceptance_criteria=None, parent_id=epic.id)
    with_ac = _workitem("RAD-19", acceptance_criteria="Given When Then", parent_id=epic.id)
    no_parent = _workitem("RAD-20", parent_id=None)
    with_parent = _workitem("RAD-21", parent_id=epic.id)
    detailed_epic = _workitem(
        "RAD-22",
        item_type=WorkItemType.EPIC,
        description="Measurable outcome " * 8,
    )
    carried = _workitem("RAD-23", parent_id=epic.id, sprint_ids=[uuid4(), uuid4()])
    not_carried = _workitem("RAD-24", parent_id=epic.id, sprint_ids=[uuid4()])
    workitems = (
        epic,
        *stories,
        no_ac,
        with_ac,
        no_parent,
        with_parent,
        detailed_epic,
        carried,
        not_carried,
    )
    # repeated-carry-over requires a sprint window (M5-05); pass a minimal sprint to set one.
    carry_sprint = Sprint(
        source=Source.JIRA,
        external_id="sprint-carry",
        board_id=_board().id,
        name="Sprint 1",
        state=SprintState.ACTIVE,
    )

    assert _matched_keys("story-without-acceptance-criteria", workitems) == {"RAD-18"}
    assert _matched_keys("story-without-parent-epic", workitems) == {"RAD-20"}
    assert _matched_keys("epic-too-broad", workitems) == {"RAD-1"}
    assert _matched_keys("epic-without-measurable-description", workitems) == {"RAD-1"}
    assert _matched_keys(
        "repeated-carry-over",
        workitems,
        capabilities=("sprint",),
        sprints=(carry_sprint,),
    ) == {"RAD-23"}
    assert set(_findings("story-without-acceptance-criteria", tuple(workitems))[0].evidence) >= {
        "scope_id",
        "workitem_type",
        "has_description",
    }
    assert set(_findings("story-without-parent-epic", tuple(workitems))[0].evidence) >= {
        "scope_id",
        "workitem_type",
    }
    assert set(_findings("epic-too-broad", tuple(workitems))[0].evidence) >= {
        "scope_id",
        "child_count",
        "threshold",
    }
    assert set(_findings("epic-without-measurable-description", tuple(workitems))[0].evidence) >= {
        "scope_id",
        "description_length",
        "threshold",
    }
    assert set(
        _findings(
            "repeated-carry-over",
            tuple(workitems),
            capabilities=("sprint",),
            sprints=(carry_sprint,),
        )[0].evidence
    ) >= {"scope_id", "sprint_count", "sprint_names"}
    stale = _workitem("RAD-25", updated_at=NOW - timedelta(days=10))
    stale_findings = _findings(
        "stale-in-progress-work-item",
        (stale,),
        transitions=(_transition(stale.id, NOW - timedelta(days=8)),),
    )
    blocked = _workitem(
        "RAD-26",
        status="Blocked",
        status_category=StatusCategory.BLOCKED,
        updated_at=NOW - timedelta(days=5),
    )
    assert set(stale_findings[0].evidence) >= {
        "scope_id",
        "days_idle",
        "last_updated_at",
        "threshold",
    }
    assert set(_findings("blocked-without-update", (blocked,))[0].evidence) >= {
        "scope_id",
        "days_blocked_idle",
        "last_updated_at",
        "threshold",
    }


def test_sprint_scope_churn_template_uses_sprint_level_evidence() -> None:
    sprint = Sprint(
        source=Source.JIRA,
        external_id="sprint-1",
        board_id=BOARD_ID,
        name="Sprint 1",
        state=SprintState.ACTIVE,
        start_date=NOW - timedelta(days=7),
    )
    original = _workitem("RAD-1", sprint_ids=[sprint.id], current_sprint_id=sprint.id)
    added = _workitem("RAD-2", sprint_ids=[sprint.id], current_sprint_id=sprint.id)
    transitions = (
        _transition(original.id, NOW - timedelta(days=8)),
        _transition(added.id, NOW - timedelta(days=2)),
    )

    findings = _findings(
        "sprint-scope-churn",
        (original, added),
        sprints=(sprint,),
        transitions=transitions,
        scope_type="board",
        capabilities=("sprint",),
    )

    assert len(findings) == 1
    assert findings[0].entity_type is EntityType.SPRINT
    assert findings[0].evidence["original_count"] == 1
    assert findings[0].evidence["added_count"] == 1
    assert findings[0].evidence["churn_pct"] == 100.0


def test_template_evidence_thresholds_use_edited_expression_values() -> None:
    item = _workitem("RAD-1", updated_at=NOW - timedelta(days=10))
    definition = instantiate_jira_signal_template("stale-in-progress-work-item")
    definition.expression["conditions"][1]["value"] = {"amount": 5, "unit": "days"}

    findings = evaluate_signal_definition(
        definition,
        SignalData(
            report_id=uuid4(),
            projects=(_project(),),
            boards=(_board(),),
            workitems=(item,),
            transitions=(_transition(item.id, NOW - timedelta(days=8)),),
        ),
        _context(None),
        JiraConnector.describe_signal_schema(),
        [_scope("project")],
    )

    assert len(findings) == 1
    assert findings[0].evidence["threshold"] == 5


def test_sprint_scope_churn_template_ignores_non_board_scopes() -> None:
    sprint = Sprint(
        source=Source.JIRA,
        external_id="sprint-1",
        board_id=BOARD_ID,
        name="Sprint 1",
        state=SprintState.ACTIVE,
        start_date=NOW - timedelta(days=7),
    )
    original = _workitem("RAD-1", sprint_ids=[sprint.id], current_sprint_id=sprint.id)
    added = _workitem("RAD-2", sprint_ids=[sprint.id], current_sprint_id=sprint.id)

    findings = _findings(
        "sprint-scope-churn",
        (original, added),
        sprints=(sprint,),
        transitions=(
            _transition(original.id, NOW - timedelta(days=8)),
            _transition(added.id, NOW - timedelta(days=2)),
        ),
        scope_type="project",
        capabilities=("sprint",),
    )

    assert findings == []


def _matched_keys(
    template_key: str,
    workitems: tuple[WorkItem, ...] | list[WorkItem],
    *,
    capabilities: tuple[str, ...] = (),
    sprints: tuple[Sprint, ...] = (),
) -> set[str]:
    return {
        finding.title.split(" ", 1)[0].split(" - ", 1)[0]
        for finding in _findings(
            template_key, tuple(workitems), capabilities=capabilities, sprints=sprints
        )
    }


def _findings(
    template_key: str,
    workitems: tuple[WorkItem, ...],
    *,
    sprints: tuple[Sprint, ...] = (),
    transitions: tuple[Transition, ...] = (),
    scope_type: str = "project",
    capabilities: tuple[str, ...] = (),
):
    return evaluate_signal_definition(
        instantiate_jira_signal_template(template_key),
        SignalData(
            report_id=uuid4(),
            projects=(_project(),),
            boards=(_board(),),
            sprints=sprints,
            workitems=workitems,
            transitions=transitions,
        ),
        _context(sprints[0].id if sprints else None),
        JiraConnector.describe_signal_schema(),
        [_scope(scope_type, capabilities)],
    )


def _scope(
    scope_type: str,
    capabilities: tuple[str, ...] = (),
) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type=scope_type,
        name="Radar",
        external_ref={"id": "BOARD" if scope_type == "board" else "PROJECT", "key": "RAD"},
        capabilities=("statuses", "labels", *capabilities),
    )


def _context(sprint_id):
    team = TeamProfile(name="Radar", created_at=NOW, updated_at=NOW)
    return EvaluationContext(
        now=NOW,
        window=EvaluationWindow(
            window_type=WindowType.SPRINT if sprint_id is not None else WindowType.DATE_RANGE,
            sprint_id=sprint_id,
            start=None if sprint_id is not None else NOW,
            end=None if sprint_id is not None else NOW,
            team_profile_id=team.id,
        ),
        team=team,
    )


def _project() -> Project:
    return Project(
        id=PROJECT_ID,
        source=Source.JIRA,
        external_id="PROJECT",
        key="RAD",
        name="Radar",
    )


def _board() -> Board:
    return Board(
        id=BOARD_ID,
        source=Source.JIRA,
        external_id="BOARD",
        project_id=PROJECT_ID,
        name="Radar Board",
        type=BoardType.SCRUM,
    )


def _workitem(
    key: str,
    *,
    item_type: WorkItemType = WorkItemType.STORY,
    description: str | None = "Description",
    acceptance_criteria: str | None = "Given When Then",
    parent_id=None,
    sprint_ids: list | None = None,
    current_sprint_id=None,
    status: str = "In Progress",
    status_category: StatusCategory = StatusCategory.IN_PROGRESS,
    updated_at: datetime | None = None,
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
        parent_id=parent_id,
        acceptance_criteria=acceptance_criteria,
        sprint_ids=sprint_ids or [],
        current_sprint_id=current_sprint_id,
        created_at=NOW - timedelta(days=10),
        updated_at=updated_at or NOW - timedelta(days=1),
    )


def _transition(entity_id, occurred_at: datetime) -> Transition:
    return Transition(
        entity_type=EntityType.WORKITEM,
        entity_id=entity_id,
        from_status="To Do",
        to_status="In Progress",
        from_status_category=StatusCategory.TODO,
        to_status_category=StatusCategory.IN_PROGRESS,
        occurred_at=occurred_at,
    )
