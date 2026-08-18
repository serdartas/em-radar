# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import model_validator
from sqlmodel import Field, SQLModel

from em_radar_core.models import WorkingMode


class TeamProfileCreate(SQLModel):
    name: str
    description: str | None = None
    connection_ids: list[UUID] = Field(default_factory=list)
    scope_ids: list[UUID] = Field(default_factory=list)
    signal_config_group_ids: list[UUID] = Field(default_factory=list)
    code_connection_id: UUID | None = None
    working_mode: WorkingMode = WorkingMode.SCRUM
    sprint_length_days: int | None = None
    member_user_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_working_mode(self) -> Self:
        if self.working_mode is WorkingMode.KANBAN and self.sprint_length_days is not None:
            raise ValueError("sprint_length_days must be null for kanban teams")
        return self


class TeamProfileUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
    connection_ids: list[UUID] | None = None
    scope_ids: list[UUID] | None = None
    signal_config_group_ids: list[UUID] | None = None
    code_connection_id: UUID | None = None
    working_mode: WorkingMode | None = None
    sprint_length_days: int | None = None
    member_user_keys: list[str] | None = None


class TeamProfileRead(TeamProfileCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime
