from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import ClassVar, Literal, Protocol, runtime_checkable

from em_radar_core.models import (
    Board,
    Comment,
    EvaluationWindow,
    MergeRequest,
    Project,
    Repository,
    Review,
    Sprint,
    Transition,
    WorkItem,
    WorkItemType,
)


@dataclass(frozen=True)
class Capabilities:
    provides_workitems: bool = False
    provides_sprints: bool = False
    provides_mergerequests: bool = False
    provides_repositories: bool = False
    provides_reviews: bool = False
    provides_comments: bool = False
    provides_transitions: bool = False
    supports_incremental_fetch: bool = False
    supports_pagination_cursor: bool = False
    max_window_days: int | None = None


@dataclass
class ConnectionTestResult:
    ok: bool
    detail: str
    user_display_name: str | None = None
    permissions: list[str] = field(default_factory=list)


@dataclass
class WorkItemScope:
    project_external_ids: list[str]
    board_external_ids: list[str] = field(default_factory=list)
    workitem_types: list[WorkItemType] | None = None


@dataclass
class MergeRequestScope:
    repository_external_ids: list[str]
    include_drafts: bool = True
    include_closed_unmerged: bool = False


@runtime_checkable
class ConnectorBase(Protocol):
    name: ClassVar[str]
    display_name: ClassVar[str]
    config_schema: ClassVar[dict[str, object]]
    min_model_version: ClassVar[int]

    def __init__(self, config: dict[str, object]) -> None: ...

    async def test_connection(self) -> ConnectionTestResult: ...

    def describe_capabilities(self) -> Capabilities: ...

    async def close(self) -> None: ...


@runtime_checkable
class WorkItemProvider(Protocol):
    async def list_projects(self) -> list[Project]: ...

    async def list_boards(self, project_id: str) -> list[Board]: ...

    async def list_sprints(self, board_id: str) -> list[Sprint]: ...

    def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]: ...


@runtime_checkable
class MergeRequestProvider(Protocol):
    async def list_repositories(self) -> list[Repository]: ...

    def fetch_mergerequests(
        self,
        scope: MergeRequestScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[MergeRequest]: ...


@runtime_checkable
class ReviewProvider(Protocol):
    def fetch_reviews(
        self,
        mergerequest_external_ids: list[str],
    ) -> AsyncIterator[Review]: ...


@runtime_checkable
class TransitionProvider(Protocol):
    def fetch_transitions(
        self,
        entity_type: Literal["workitem", "mergerequest"],
        entity_external_ids: list[str],
    ) -> AsyncIterator[Transition]: ...


@runtime_checkable
class CommentProvider(Protocol):
    def fetch_comments(
        self,
        entity_type: Literal["workitem", "mergerequest"],
        entity_external_ids: list[str],
    ) -> AsyncIterator[Comment]: ...


class ConnectorError(Exception):
    pass


class ConnectorAuthError(ConnectorError):
    pass


class ConnectorNotFoundError(ConnectorError):
    pass


class ConnectorRateLimitedError(ConnectorError):
    pass


class ConnectorTransientError(ConnectorError):
    pass


class ConnectorConfigError(ConnectorError):
    pass


class ConnectorDataError(ConnectorError):
    pass


__all__ = [
    "Capabilities",
    "CommentProvider",
    "ConnectionTestResult",
    "ConnectorAuthError",
    "ConnectorBase",
    "ConnectorConfigError",
    "ConnectorDataError",
    "ConnectorError",
    "ConnectorNotFoundError",
    "ConnectorRateLimitedError",
    "ConnectorTransientError",
    "MergeRequestProvider",
    "MergeRequestScope",
    "ReviewProvider",
    "TransitionProvider",
    "WorkItemProvider",
    "WorkItemScope",
]
