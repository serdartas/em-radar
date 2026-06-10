from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from em_radar_core.models import (
    Board,
    Comment,
    EvaluationContext,
    MergeRequest,
    Project,
    Repository,
    Review,
    Severity,
    SignalFinding,
    Sprint,
    Transition,
    WorkItem,
)


class SignalParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class SignalData:
    """Source-agnostic canonical data available during one report evaluation."""

    report_id: UUID
    projects: tuple[Project, ...] = field(default_factory=tuple)
    boards: tuple[Board, ...] = field(default_factory=tuple)
    sprints: tuple[Sprint, ...] = field(default_factory=tuple)
    workitems: tuple[WorkItem, ...] = field(default_factory=tuple)
    repositories: tuple[Repository, ...] = field(default_factory=tuple)
    mergerequests: tuple[MergeRequest, ...] = field(default_factory=tuple)
    reviews: tuple[Review, ...] = field(default_factory=tuple)
    transitions: tuple[Transition, ...] = field(default_factory=tuple)
    comments: tuple[Comment, ...] = field(default_factory=tuple)


class Signal(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    default_severity: ClassVar[Severity]
    params_schema: ClassVar[type[SignalParams]]

    def __init__(self, params: Mapping[str, object] | None = None) -> None:
        self.params = self.params_schema.model_validate(params or {})

    @abstractmethod
    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        """Evaluate canonical data using `ctx.now` as the only current-time source."""

