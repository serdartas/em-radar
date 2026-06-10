from collections.abc import AsyncIterator, Iterable
from typing import ClassVar, Literal, TypeVar

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    MergeRequestScope,
    WorkItemScope,
)
from em_radar_core.models import (
    Board,
    Comment,
    EntityType,
    EvaluationWindow,
    MergeRequest,
    MergeRequestState,
    Project,
    Repository,
    Review,
    Sprint,
    Transition,
    WindowType,
    WorkItem,
)
from sqlmodel import SQLModel

from em_radar_connector_demo.fixtures import DemoFixtures, build_fixtures

ModelT = TypeVar("ModelT", bound=SQLModel)


class DemoConnector:
    """Deterministic, credential-free connector used by the demo report path."""

    name: ClassVar[str] = "demo"
    display_name: ClassVar[str] = "Demo company"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        self.config = dict(config)
        self._fixtures: DemoFixtures = build_fixtures()

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            ok=True,
            detail="Demo company data is ready",
            user_display_name="Demo User",
            permissions=["read"],
        )

    def describe_capabilities(self) -> Capabilities:
        return Capabilities(
            provides_workitems=True,
            provides_sprints=True,
            provides_mergerequests=True,
            provides_repositories=True,
            provides_reviews=True,
            provides_comments=True,
            provides_transitions=True,
        )

    async def close(self) -> None:
        pass

    async def list_projects(self) -> list[Project]:
        return _copies(self._fixtures.projects)

    async def list_boards(self, project_id: str) -> list[Board]:
        project_ids = {
            project.id
            for project in self._fixtures.projects
            if project.external_id == project_id or str(project.id) == project_id
        }
        return _copies(
            board
            for board in self._fixtures.boards
            if board.project_id in project_ids
        )

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        board_ids = {
            board.id
            for board in self._fixtures.boards
            if board.external_id == board_id or str(board.id) == board_id
        }
        return _copies(
            sprint
            for sprint in self._fixtures.sprints
            if sprint.board_id in board_ids
        )

    async def list_repositories(self) -> list[Repository]:
        return _copies(self._fixtures.repositories)

    async def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]:
        project_ids = set(scope.project_external_ids)
        board_ids = set(scope.board_external_ids)
        allowed_projects = {
            project.id
            for project in self._fixtures.projects
            if project.external_id in project_ids or str(project.id) in project_ids
        }
        if board_ids:
            allowed_projects.update(
                board.project_id
                for board in self._fixtures.boards
                if board.external_id in board_ids or str(board.id) in board_ids
            )
        allowed_types = set(scope.workitem_types) if scope.workitem_types is not None else None

        for item in self._fixtures.workitems:
            if item.project_id not in allowed_projects:
                continue
            if allowed_types is not None and item.type not in allowed_types:
                continue
            if not _workitem_in_window(item, window):
                continue
            yield item.model_copy(deep=True)

    async def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]:
        repository_ids = set(scope.repository_external_ids)
        allowed_repositories = {
            repository.id
            for repository in self._fixtures.repositories
            if repository.external_id in repository_ids or str(repository.id) in repository_ids
        }
        for merge_request in self._fixtures.mergerequests:
            if merge_request.repository_id not in allowed_repositories:
                continue
            if merge_request.is_draft and not scope.include_drafts:
                continue
            if (
                merge_request.state is MergeRequestState.CLOSED
                and not scope.include_closed_unmerged
            ):
                continue
            if not _mergerequest_in_window(merge_request, window):
                continue
            yield merge_request.model_copy(deep=True)

    async def fetch_reviews(
        self,
        mergerequest_external_ids: list[str],
    ) -> AsyncIterator[Review]:
        entity_ids = _entity_ids(self._fixtures.mergerequests, mergerequest_external_ids)
        async for review in _yield_matching(self._fixtures.reviews, entity_ids, "mergerequest_id"):
            yield review

    async def fetch_transitions(
        self,
        entity_type: Literal["workitem", "mergerequest"],
        entity_external_ids: list[str],
    ) -> AsyncIterator[Transition]:
        entities = (
            self._fixtures.workitems
            if entity_type == EntityType.WORKITEM
            else self._fixtures.mergerequests
        )
        entity_ids = _entity_ids(entities, entity_external_ids)
        for transition in self._fixtures.transitions:
            if transition.entity_type == entity_type and transition.entity_id in entity_ids:
                yield transition.model_copy(deep=True)

    async def fetch_comments(
        self,
        entity_type: Literal["workitem", "mergerequest"],
        entity_external_ids: list[str],
    ) -> AsyncIterator[Comment]:
        entities = (
            self._fixtures.workitems
            if entity_type == EntityType.WORKITEM
            else self._fixtures.mergerequests
        )
        entity_ids = _entity_ids(entities, entity_external_ids)
        for comment in self._fixtures.comments:
            if comment.entity_type == entity_type and comment.entity_id in entity_ids:
                yield comment.model_copy(deep=True)


def _copies(models: Iterable[ModelT]) -> list[ModelT]:
    return [model.model_copy(deep=True) for model in models]


def _entity_ids(models: Iterable[ModelT], external_ids: list[str]) -> set[object]:
    requested_ids = set(external_ids)
    return {
        model.id
        for model in models
        if getattr(model, "external_id", None) in requested_ids or str(model.id) in requested_ids
    }


async def _yield_matching(
    models: Iterable[ModelT],
    entity_ids: set[object],
    field_name: str,
) -> AsyncIterator[ModelT]:
    for model in models:
        if getattr(model, field_name) in entity_ids:
            yield model.model_copy(deep=True)


def _workitem_in_window(item: WorkItem, window: EvaluationWindow) -> bool:
    if window.window_type is WindowType.SPRINT:
        return window.sprint_id in item.sprint_ids
    if window.start is None or window.end is None or item.created_at is None:
        return False
    return item.created_at <= window.end and (
        item.resolved_at is None or item.resolved_at >= window.start
    )


def _mergerequest_in_window(merge_request: MergeRequest, window: EvaluationWindow) -> bool:
    if window.window_type is WindowType.SPRINT:
        return True
    if window.start is None or window.end is None:
        return False
    terminal_at = merge_request.merged_at or merge_request.closed_at
    return merge_request.created_at <= window.end and (
        terminal_at is None or terminal_at >= window.start
    )
