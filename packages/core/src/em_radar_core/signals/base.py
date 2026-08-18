# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from uuid import UUID

from em_radar_core.models import (
    Board,
    Comment,
    MergeRequest,
    Project,
    Repository,
    Review,
    Sprint,
    Transition,
    WorkItem,
)


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
