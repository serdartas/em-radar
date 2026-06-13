from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5

from em_radar_core.models import (
    Board,
    BoardType,
    Comment,
    EntityType,
    MergeRequest,
    MergeRequestState,
    PipelineStatus,
    Project,
    Repository,
    Review,
    ReviewDecision,
    Source,
    Sprint,
    SprintState,
    StatusCategory,
    Transition,
    User,
    WorkItem,
    WorkItemType,
)

FIXTURE_NOW = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
_NAMESPACE = UUID("d68a6308-cb59-45ee-a6f5-2c2d781b89d7")

DEMO_USER_COUNT = 6
DEMO_PROJECT_COUNT = 3
DEMO_SPRINT_COUNT = 3
DEMO_WORKITEM_COUNT = 30
DEMO_REPOSITORY_COUNT = 3
DEMO_MERGEREQUEST_COUNT = 10
DEMO_REVIEW_COUNT = 8
DEMO_TRANSITION_COUNT = 20
DEMO_COMMENT_COUNT = 12


def stable_id(kind: str, external_id: str) -> UUID:
    return uuid5(_NAMESPACE, f"{kind}:{external_id}")


@dataclass(frozen=True)
class DemoFixtures:
    users: tuple[User, ...]
    projects: tuple[Project, ...]
    boards: tuple[Board, ...]
    sprints: tuple[Sprint, ...]
    workitems: tuple[WorkItem, ...]
    repositories: tuple[Repository, ...]
    mergerequests: tuple[MergeRequest, ...]
    reviews: tuple[Review, ...]
    transitions: tuple[Transition, ...]
    comments: tuple[Comment, ...]


def build_fixtures() -> DemoFixtures:
    users = _build_users()
    projects = _build_projects()
    boards = _build_boards(projects)
    sprints = _build_sprints(boards[0])
    workitems = _build_workitems(projects, sprints)
    repositories = _build_repositories()
    mergerequests = _build_mergerequests(repositories, workitems)
    reviews = _build_reviews(mergerequests)
    transitions = _build_transitions(workitems)
    comments = _build_comments(workitems, mergerequests)
    return DemoFixtures(
        users=users,
        projects=projects,
        boards=boards,
        sprints=sprints,
        workitems=workitems,
        repositories=repositories,
        mergerequests=mergerequests,
        reviews=reviews,
        transitions=transitions,
        comments=comments,
    )


def _common(kind: str, external_id: str, *, age_days: int = 60) -> dict[str, object]:
    return {
        "id": stable_id(kind, external_id),
        "source": Source.DEMO,
        "external_id": external_id,
        "source_url": f"https://demo.emradar.dev/{kind}/{external_id}",
        "source_metadata": {},
        "fetched_at": FIXTURE_NOW,
        "created_at": FIXTURE_NOW - timedelta(days=age_days),
        "updated_at": FIXTURE_NOW - timedelta(days=1),
    }


def _build_users() -> tuple[User, ...]:
    return tuple(
        User(
            **_common("user", f"user-{number}", age_days=400),
            display_name=f"Demo User {number}",
            email=f"user{number}@demo.emradar.dev",
            username=f"demo-user-{number}",
            is_bot=number == DEMO_USER_COUNT,
        )
        for number in range(1, DEMO_USER_COUNT + 1)
    )


def _build_projects() -> tuple[Project, ...]:
    definitions = (
        ("platform", "PLAT", "Platform"),
        ("checkout", "CHECK", "Checkout"),
        ("mobile", "MOB", "Mobile"),
    )
    return tuple(
        Project(**_common("project", external_id), key=key, name=name)
        for external_id, key, name in definitions
    )


def _build_boards(projects: tuple[Project, ...]) -> tuple[Board, ...]:
    return tuple(
        Board(
            **_common("board", f"{project.external_id}-delivery"),
            project_id=project.id,
            name=f"{project.name} Delivery",
            type=BoardType.SCRUM,
        )
        for project in projects
    )


def _build_sprints(board: Board) -> tuple[Sprint, ...]:
    definitions = (
        ("sprint-22", "Sprint 22", SprintState.CLOSED, -42, -28),
        ("sprint-23", "Sprint 23", SprintState.CLOSED, -28, -14),
        ("sprint-24", "Sprint 24", SprintState.ACTIVE, -14, 0),
    )
    return tuple(
        Sprint(
            **_common("sprint", external_id, age_days=70),
            board_id=board.id,
            name=name,
            state=state,
            start_date=FIXTURE_NOW + timedelta(days=start_offset),
            end_date=FIXTURE_NOW + timedelta(days=end_offset),
            complete_date=(
                FIXTURE_NOW + timedelta(days=end_offset) if state is SprintState.CLOSED else None
            ),
            goal="Improve delivery flow",
        )
        for external_id, name, state, start_offset, end_offset in definitions
    )


def _build_workitems(
    projects: tuple[Project, ...],
    sprints: tuple[Sprint, ...],
) -> tuple[WorkItem, ...]:
    types = (
        WorkItemType.EPIC,
        WorkItemType.STORY,
        WorkItemType.TASK,
        WorkItemType.BUG,
        WorkItemType.SPIKE,
        WorkItemType.SUBTASK,
    )
    items: list[WorkItem] = []
    for number in range(1, DEMO_WORKITEM_COUNT + 1):
        project_index = (number - 1) // 10
        project = projects[project_index]
        item_type = types[(number - 1) % len(types)]
        parent_id = _epic_parent_id(number, project_index, item_type)
        external_id = f"workitem-{number}"
        status_category, status, is_blocked = _workitem_status(number)
        resolved_at = (
            FIXTURE_NOW - timedelta(days=number % 6 + 1)
            if status_category is StatusCategory.DONE
            else None
        )
        updated_days = 12 if number in {2, 4, 7, 8, 14, 16, 22, 28} else number % 5
        sprint_ids: list[UUID] = []
        current_sprint_id: UUID | None = None
        if number <= 18:
            sprint_ids = [sprints[2].id]
            current_sprint_id = sprints[2].id
        if number in {2, 7, 14}:
            sprint_ids = [sprints[0].id, sprints[1].id, sprints[2].id]
        elif number in {4, 8, 16}:
            sprint_ids = [sprints[1].id, sprints[2].id]
        elif 19 <= number <= 24:
            sprint_ids = [sprints[1].id]

        values = _common("workitem", external_id, age_days=35 + number)
        values["updated_at"] = FIXTURE_NOW - timedelta(days=updated_days)
        items.append(
            WorkItem(
                **values,
                project_id=project.id,
                key=f"{project.key}-{number}",
                type=item_type,
                title=f"Demo delivery item {number}",
                description=f"Normalized demo work item {number}.",
                status=status,
                status_category=status_category,
                assignee_id=None
                if number in {7, 21}
                else stable_id("user", f"user-{number % 6 + 1}"),
                reporter_id=stable_id("user", "user-1"),
                labels=["blocked"] if is_blocked else [f"area-{number % 3 + 1}"],
                components=[project.key.lower()],
                story_points=float((number % 5) + 1),
                acceptance_criteria=None
                if number % 4 == 0
                else "The expected behavior is verified.",
                is_blocked=is_blocked,
                parent_id=parent_id,
                resolved_at=resolved_at,
                due_date=FIXTURE_NOW + timedelta(days=number % 10 - 3),
                sprint_ids=sprint_ids,
                current_sprint_id=current_sprint_id,
            )
        )
    return tuple(items)


def _epic_parent_id(number: int, project_index: int, item_type: WorkItemType) -> UUID | None:
    if item_type is WorkItemType.EPIC:
        return None
    project_start = project_index * 10 + 1
    first_epic = next(
        candidate
        for candidate in range(project_start, project_start + 10)
        if (candidate - 1) % 6 == 0
    )
    return stable_id("workitem", f"workitem-{first_epic}")


def _workitem_status(number: int) -> tuple[StatusCategory, str, bool]:
    if number % 5 == 0:
        return StatusCategory.DONE, "Done", False
    if number % 7 == 0:
        return StatusCategory.BLOCKED, "Blocked", True
    if number % 2 == 0:
        return StatusCategory.IN_PROGRESS, "In Progress", False
    return StatusCategory.TODO, "To Do", False


def _build_repositories() -> tuple[Repository, ...]:
    definitions = (
        ("platform-api", "Platform API", "engineering/platform-api"),
        ("checkout-service", "Checkout Service", "commerce/checkout-service"),
        ("mobile-app", "Mobile App", "products/mobile-app"),
    )
    return tuple(
        Repository(
            **_common("repository", external_id, age_days=300),
            name=name,
            full_path=full_path,
            default_branch="main",
        )
        for external_id, name, full_path in definitions
    )


def _build_mergerequests(
    repositories: tuple[Repository, ...],
    workitems: tuple[WorkItem, ...],
) -> tuple[MergeRequest, ...]:
    states = (
        MergeRequestState.OPEN,
        MergeRequestState.OPEN,
        MergeRequestState.DRAFT,
        MergeRequestState.MERGED,
        MergeRequestState.MERGED,
        MergeRequestState.CLOSED,
        MergeRequestState.OPEN,
        MergeRequestState.OPEN,
        MergeRequestState.MERGED,
        MergeRequestState.OPEN,
    )
    pipelines = (
        PipelineStatus.SUCCESS,
        PipelineStatus.FAILED,
        PipelineStatus.RUNNING,
        PipelineStatus.SUCCESS,
        PipelineStatus.SUCCESS,
        PipelineStatus.CANCELED,
        PipelineStatus.FAILED,
        PipelineStatus.NONE,
        PipelineStatus.SUCCESS,
        PipelineStatus.SUCCESS,
    )
    merge_requests: list[MergeRequest] = []
    for number, state in enumerate(states, start=1):
        external_id = f"mr-{number}"
        created_at = FIXTURE_NOW - timedelta(days=number + 2)
        updated_at = FIXTURE_NOW - timedelta(days=10 if number in {2, 7} else number % 3)
        terminal_at = FIXTURE_NOW - timedelta(days=number % 4 + 1)
        linked_item = workitems[number - 1]
        values = _common("mergerequest", external_id, age_days=number + 2)
        values["created_at"] = created_at
        values["updated_at"] = updated_at
        merge_requests.append(
            MergeRequest(
                **values,
                repository_id=repositories[(number - 1) % len(repositories)].id,
                iid=number,
                title=f"{linked_item.key}: Demo change {number}",
                description=f"Implements {linked_item.key}.",
                state=state,
                is_draft=state is MergeRequestState.DRAFT,
                author_id=stable_id("user", f"user-{number % 6 + 1}"),
                target_branch="main",
                source_branch=f"feature/{linked_item.key.lower()}",
                merged_at=terminal_at if state is MergeRequestState.MERGED else None,
                closed_at=terminal_at if state is MergeRequestState.CLOSED else None,
                changed_files_count=number * 3,
                additions=number * 45,
                deletions=number * 7,
                pipeline_status=pipelines[number - 1],
                pipeline_updated_at=updated_at,
                approval_count=number % 3,
                comment_count=number % 4,
                linked_workitem_keys=[linked_item.key],
                linked_workitem_ids=[linked_item.id],
            )
        )
    return tuple(merge_requests)


def _build_reviews(merge_requests: tuple[MergeRequest, ...]) -> tuple[Review, ...]:
    decisions = (
        ReviewDecision.APPROVED,
        ReviewDecision.REQUESTED,
        ReviewDecision.CHANGES_REQUESTED,
        ReviewDecision.COMMENTED,
        ReviewDecision.APPROVED,
        ReviewDecision.REQUESTED,
        ReviewDecision.APPROVED,
        ReviewDecision.DISMISSED,
    )
    return tuple(
        Review(
            id=stable_id("review", f"review-{number}"),
            mergerequest_id=merge_requests[(number - 1) % len(merge_requests)].id,
            reviewer_id=stable_id("user", f"user-{number % 6 + 1}"),
            decision=decision,
            submitted_at=(
                None
                if decision is ReviewDecision.REQUESTED
                else FIXTURE_NOW - timedelta(hours=number * 4)
            ),
        )
        for number, decision in enumerate(decisions, start=1)
    )


def _build_transitions(workitems: tuple[WorkItem, ...]) -> tuple[Transition, ...]:
    transitions: list[Transition] = []
    for number, workitem in enumerate(workitems[:DEMO_TRANSITION_COUNT], start=1):
        to_category = workitem.status_category
        transitions.append(
            Transition(
                id=stable_id("transition", f"transition-{number}"),
                entity_type=EntityType.WORKITEM,
                entity_id=workitem.id,
                from_status="To Do",
                to_status=workitem.status,
                from_status_category=StatusCategory.TODO,
                to_status_category=to_category,
                actor_id=stable_id("user", f"user-{number % 6 + 1}"),
                occurred_at=FIXTURE_NOW - timedelta(days=number % 12 + 1),
            )
        )
    return tuple(transitions)


def _build_comments(
    workitems: tuple[WorkItem, ...],
    merge_requests: tuple[MergeRequest, ...],
) -> tuple[Comment, ...]:
    comments: list[Comment] = []
    for number in range(1, DEMO_COMMENT_COUNT + 1):
        is_workitem = number <= 7
        entity = workitems[number - 1] if is_workitem else merge_requests[number - 8]
        external_id = f"comment-{number}"
        comments.append(
            Comment(
                id=stable_id("comment", external_id),
                source=Source.DEMO,
                external_id=external_id,
                entity_type=EntityType.WORKITEM if is_workitem else EntityType.MERGEREQUEST,
                entity_id=entity.id,
                author_id=stable_id("user", f"user-{number % 6 + 1}"),
                body=f"Deterministic demo comment {number}.",
                created_at=FIXTURE_NOW - timedelta(hours=number * 6),
                updated_at=None,
                is_system=number in {3, 9},
            )
        )
    return tuple(comments)
