from datetime import datetime, timezone
from uuid import UUID, uuid4

from em_radar_core.models import (
    Board,
    EntityType,
    EvaluationContext,
    EvaluationWindow,
    Project,
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

NOW = datetime(2026, 1, 20, 12, tzinfo=timezone.utc)
PROJECT_ID = uuid4()
BOARD_ID = uuid4()


def context(sprint_id: UUID | None = None) -> EvaluationContext:
    team = TeamProfile(
        name="Signal test team",
        project_ids=[PROJECT_ID],
        repository_ids=[],
        created_at=NOW,
        updated_at=NOW,
    )
    window = (
        EvaluationWindow(
            window_type=WindowType.SPRINT,
            sprint_id=sprint_id or uuid4(),
            team_profile_id=team.id,
        )
        if sprint_id is not None
        else EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=NOW,
            end=NOW,
            team_profile_id=team.id,
        )
    )
    return EvaluationContext(now=NOW, window=window, team=team)


def project() -> Project:
    return Project(
        id=PROJECT_ID,
        source=Source.JIRA,
        external_id="PROJECT",
        key="RAD",
        name="Radar",
    )


def board() -> Board:
    return Board(
        id=BOARD_ID,
        source=Source.JIRA,
        external_id="BOARD",
        project_id=PROJECT_ID,
        name="Board",
    )


def sprint(name: str = "Sprint 1", start_date: datetime | None = None) -> Sprint:
    return Sprint(
        source=Source.JIRA,
        external_id=name,
        board_id=BOARD_ID,
        name=name,
        state=SprintState.ACTIVE,
        start_date=start_date,
    )


def workitem(
    key: str = "RAD-1",
    *,
    item_type: WorkItemType = WorkItemType.STORY,
    status_category: StatusCategory = StatusCategory.IN_PROGRESS,
    status: str = "In Progress",
    description: str | None = "Description",
    acceptance_criteria: str | None = "Given When Then",
    labels: list[str] | None = None,
    parent_id: UUID | None = None,
    is_blocked: bool = False,
    sprint_ids: list[UUID] | None = None,
    current_sprint_id: UUID | None = None,
    created_at: datetime | None = None,
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
        labels=labels or [],
        parent_id=parent_id,
        acceptance_criteria=acceptance_criteria,
        is_blocked=is_blocked,
        resolved_at=NOW if status_category is StatusCategory.DONE else None,
        sprint_ids=sprint_ids or [],
        current_sprint_id=current_sprint_id,
        created_at=created_at,
        updated_at=updated_at,
    )


def transition(
    entity_id: UUID,
    *,
    occurred_at: datetime,
    to_status_category: StatusCategory,
    from_status_category: StatusCategory | None = StatusCategory.TODO,
) -> Transition:
    return Transition(
        entity_type=EntityType.WORKITEM,
        entity_id=entity_id,
        from_status="To Do",
        to_status=to_status_category.value,
        from_status_category=from_status_category,
        to_status_category=to_status_category,
        occurred_at=occurred_at,
    )
