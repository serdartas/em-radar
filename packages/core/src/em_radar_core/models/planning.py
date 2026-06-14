from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from pydantic import model_validator
from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

from em_radar_core.models.common import CommonFields, UUIDListJSON
from em_radar_core.models.enums import (
    BoardType,
    LinkType,
    SprintState,
    StatusCategory,
    WorkItemType,
)


class User(CommonFields):
    display_name: str
    email: str | None = None
    username: str | None = None
    is_bot: bool = False


class Project(CommonFields):
    key: str
    name: str


class Board(CommonFields):
    project_id: UUID
    name: str
    type: BoardType | None = None


class Sprint(CommonFields):
    board_id: UUID
    name: str
    state: SprintState
    start_date: datetime | None = None
    end_date: datetime | None = None
    complete_date: datetime | None = None
    goal: str | None = None


class WorkItem(CommonFields):
    project_id: UUID
    key: str
    type: WorkItemType
    title: str
    description: str | None = None
    status: str
    status_category: StatusCategory
    assignee_id: UUID | None = None
    reporter_id: UUID | None = None
    labels: list[str] = Field(default_factory=list, sa_type=JSON)
    components: list[str] = Field(default_factory=list, sa_type=JSON)
    parent_id: UUID | None = None
    story_points: float | None = None
    acceptance_criteria: str | None = None
    is_blocked: bool = False
    resolved_at: datetime | None = None
    due_date: datetime | None = None
    sprint_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)
    current_sprint_id: UUID | None = None

    @model_validator(mode="after")
    def validate_invariants(self) -> Self:
        if self.parent_id == self.id:
            raise ValueError("parent_id cannot reference the work item itself")
        if self.type is WorkItemType.EPIC and self.parent_id is not None:
            raise ValueError("epics cannot have a parent in MVP")
        if self.current_sprint_id is not None and self.current_sprint_id not in self.sprint_ids:
            raise ValueError("current_sprint_id must be present in sprint_ids")
        if (self.status_category is StatusCategory.DONE) != (self.resolved_at is not None):
            raise ValueError("resolved_at must be set if and only if status_category is done")
        return self


class WorkItemLink(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    source_workitem_id: UUID
    target_workitem_id: UUID
    link_type: LinkType

    @classmethod
    def canonical_pair(
        cls,
        source_workitem_id: UUID,
        target_workitem_id: UUID,
        link_type: LinkType,
    ) -> tuple[Self, Self]:
        canonical_types = {
            LinkType.BLOCKS: (LinkType.BLOCKS, LinkType.IS_BLOCKED_BY, False),
            LinkType.IS_BLOCKED_BY: (LinkType.BLOCKS, LinkType.IS_BLOCKED_BY, True),
            LinkType.DUPLICATES: (LinkType.DUPLICATES, LinkType.IS_DUPLICATED_BY, False),
            LinkType.IS_DUPLICATED_BY: (LinkType.DUPLICATES, LinkType.IS_DUPLICATED_BY, True),
        }
        canonical = canonical_types.get(link_type)
        if canonical is None:
            raise ValueError(f"{link_type} is not an asymmetric link type")
        forward_type, inverse_type, reverse_direction = canonical
        if reverse_direction:
            source_workitem_id, target_workitem_id = target_workitem_id, source_workitem_id

        return (
            cls(
                source_workitem_id=source_workitem_id,
                target_workitem_id=target_workitem_id,
                link_type=forward_type,
            ),
            cls(
                source_workitem_id=target_workitem_id,
                target_workitem_id=source_workitem_id,
                link_type=inverse_type,
            ),
        )
