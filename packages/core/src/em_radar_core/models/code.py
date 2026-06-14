from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from pydantic import model_validator
from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

from em_radar_core.models.common import CommonFields, UUIDListJSON
from em_radar_core.models.enums import (
    EntityType,
    MergeRequestState,
    PipelineStatus,
    ReviewDecision,
    Source,
    StatusCategory,
)


class Repository(CommonFields):
    name: str
    full_path: str
    default_branch: str
    is_archived: bool = False


class MergeRequest(CommonFields):
    repository_id: UUID
    iid: int
    title: str
    description: str | None = None
    state: MergeRequestState
    is_draft: bool = False
    author_id: UUID
    target_branch: str
    source_branch: str
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    changed_files_count: int | None = None
    additions: int | None = None
    deletions: int | None = None
    pipeline_status: PipelineStatus | None = None
    pipeline_updated_at: datetime | None = None
    approval_count: int = 0
    comment_count: int = 0
    linked_workitem_keys: list[str] = Field(default_factory=list, sa_type=JSON)
    linked_workitem_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)

    @model_validator(mode="after")
    def validate_invariants(self) -> Self:
        if self.state is MergeRequestState.MERGED and self.merged_at is None:
            raise ValueError("merged merge requests require merged_at")
        if self.state is MergeRequestState.CLOSED and self.closed_at is None:
            raise ValueError("closed merge requests require closed_at")
        if self.merged_at is not None and self.closed_at is not None:
            raise ValueError("merged_at and closed_at are mutually exclusive")
        return self


class Review(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    mergerequest_id: UUID
    reviewer_id: UUID
    decision: ReviewDecision
    submitted_at: datetime | None = None


class Comment(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    source: Source
    external_id: str
    entity_type: EntityType
    entity_id: UUID
    author_id: UUID
    body: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    is_system: bool = False

    @model_validator(mode="after")
    def validate_entity_type(self) -> Self:
        _validate_history_entity_type(self.entity_type)
        return self


class Transition(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    entity_type: EntityType
    entity_id: UUID
    from_status: str | None = None
    to_status: str
    from_status_category: StatusCategory | None = None
    to_status_category: StatusCategory
    actor_id: UUID | None = None
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_entity_type(self) -> Self:
        _validate_history_entity_type(self.entity_type)
        return self


def _validate_history_entity_type(entity_type: EntityType) -> None:
    if entity_type not in {EntityType.WORKITEM, EntityType.MERGEREQUEST}:
        raise ValueError("history entities must reference a workitem or mergerequest")
