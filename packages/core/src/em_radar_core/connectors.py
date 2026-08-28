# SPDX-License-Identifier: Apache-2.0

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
    provides_members: bool = False
    supports_incremental_fetch: bool = False
    supports_pagination_cursor: bool = False
    max_window_days: int | None = None


@dataclass(frozen=True)
class ValueProvider:
    type: str
    source: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class FieldAvailability:
    requires_scope_capability: tuple[str, ...] = ()


@dataclass(frozen=True)
class SignalField:
    key: str
    label: str
    type: str
    operators: tuple[str, ...]
    values: tuple[object, ...] = ()
    value_provider: ValueProvider | None = None
    availability: FieldAvailability | None = None
    entity_type: str | None = None


@dataclass(frozen=True)
class SignalScopeType:
    key: str
    label: str
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class SignalCapabilitySchema:
    connector_type: str
    entity_types: tuple[str, ...]
    scope_types: tuple[SignalScopeType, ...]
    fields: tuple[SignalField, ...]
    custom_field_entity_types: frozenset[str] = field(default_factory=frozenset)


ConnectionErrorCode = Literal[
    "auth",
    "config",
    "data",
    "not_found",
    "rate_limited",
    "transient",
    "unknown",
]


@dataclass
class ConnectionTestResult:
    ok: bool
    detail: str
    user_display_name: str | None = None
    permissions: list[str] = field(default_factory=list)
    code: ConnectionErrorCode | None = None


@dataclass
class WorkItemScope:
    project_external_ids: list[str]
    board_external_ids: list[str] = field(default_factory=list)
    workitem_types: list[WorkItemType] | None = None
    sprint_external_id: str | None = None
    custom_field_ids: list[str] = field(default_factory=list)


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

    @classmethod
    def describe_capabilities(cls) -> Capabilities: ...

    @classmethod
    def describe_signal_schema(cls) -> SignalCapabilitySchema: ...

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


@dataclass(frozen=True)
class MemberRef:
    provider_user_id: str
    username: str
    display_name: str
    avatar_url: str | None = None


@runtime_checkable
class MemberProvider(Protocol):
    async def search_users(self, query: str, *, limit: int) -> list[MemberRef]: ...

    async def get_user(self, provider_user_id: str) -> MemberRef | None: ...


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
    "ConnectionErrorCode",
    "ConnectionTestResult",
    "ConnectorAuthError",
    "ConnectorBase",
    "ConnectorConfigError",
    "ConnectorDataError",
    "ConnectorError",
    "ConnectorNotFoundError",
    "ConnectorRateLimitedError",
    "ConnectorTransientError",
    "FieldAvailability",
    "MemberProvider",
    "MemberRef",
    "MergeRequestProvider",
    "MergeRequestScope",
    "ReviewProvider",
    "SignalCapabilitySchema",
    "SignalField",
    "SignalScopeType",
    "TransitionProvider",
    "ValueProvider",
    "WorkItemProvider",
    "WorkItemScope",
]
