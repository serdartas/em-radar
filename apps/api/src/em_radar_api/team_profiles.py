# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import model_validator
from sqlmodel import Field, SQLModel

from em_radar_core.models import ScopeVerificationStatus, WorkingMode


class TeamProfileCreate(SQLModel):
    name: str
    description: str | None = None
    connection_ids: list[UUID] = Field(default_factory=list)
    scope_ids: list[UUID] = Field(default_factory=list)
    signal_config_group_ids: list[UUID] = Field(default_factory=list)
    code_connection_id: UUID | None = None
    working_mode: WorkingMode = WorkingMode.SCRUM
    sprint_length_days: int | None = None

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


class GitLabConfigStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    CONFIGURED = "configured"
    SETUP_REQUIRED = "setup_required"


class TeamProfileRead(TeamProfileCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime
    gitlab_config_status: GitLabConfigStatus = GitLabConfigStatus.NOT_APPLICABLE


class TeamGitLabMemberRead(SQLModel):
    id: UUID
    team_profile_id: UUID
    connection_id: UUID | None
    gitlab_user_id: int
    username: str
    display_name: str | None
    verification_status: ScopeVerificationStatus
    created_at: datetime
    updated_at: datetime


class TeamGitLabRepositoryRead(SQLModel):
    id: UUID
    team_profile_id: UUID
    connection_id: UUID | None
    gitlab_project_id: int
    name: str
    path_with_namespace: str
    verification_status: ScopeVerificationStatus
    created_at: datetime
    updated_at: datetime


class GitLabMemberInput(SQLModel):
    gitlab_user_id: int


class GitLabRepositoryInput(SQLModel):
    gitlab_project_id: int


class MemberSearchResult(SQLModel):
    provider_user_id: str
    username: str
    display_name: str
    avatar_url: str | None = None


class ProjectSearchResult(SQLModel):
    provider_project_id: str
    name: str
    path_with_namespace: str


class RepositoryActivityResult(SQLModel):
    provider_project_id: str
    name: str
    path_with_namespace: str
    contributing_member_count: int
    merge_request_count: int
    last_activity_at: datetime


class RepositorySuggestionsResponse(SQLModel):
    """Response envelope for the repository-suggestions endpoint.

    window_days reports the discovery window that was actually used (default or widened).
    repositories is the ranked list of candidate repositories for that window.
    """

    window_days: int
    repositories: list[RepositoryActivityResult]
