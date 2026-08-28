# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from em_radar_api.models.signal_pack_history import SignalPackHistory  # noqa: F401
from em_radar_api.scope_definitions import ScopeDefinitionTable  # noqa: F401
from em_radar_api.signal_config_groups import SignalConfigGroupTable  # noqa: F401
from em_radar_api.signal_definitions import SignalDefinitionTable  # noqa: F401
from em_radar_api.source_connections import SourceConnectionTable, UUIDListJSON  # noqa: F401

from em_radar_core.models import (
    Board,
    Comment,
    EvaluationWindow,
    MergeRequest,
    Project,
    Report,
    Repository,
    Review,
    SignalFinding,
    Sprint,
    TeamGitLabMember,
    TeamGitLabRepository,
    TeamProfile,
    Transition,
    User,
    WorkItem,
    WorkItemLink,
)


class UserTable(User, table=True):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)


class ProjectTable(Project, table=True):
    __tablename__ = "project"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)


class BoardTable(Board, table=True):
    __tablename__ = "board"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")


class SprintTable(Sprint, table=True):
    __tablename__ = "sprint"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    board_id: UUID = Field(foreign_key="board.id")


class WorkItemTable(WorkItem, table=True):
    __tablename__ = "work_item"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    assignee_id: UUID | None = Field(default=None, foreign_key="user.id")
    reporter_id: UUID | None = Field(default=None, foreign_key="user.id")
    parent_id: UUID | None = Field(default=None, foreign_key="work_item.id")
    current_sprint_id: UUID | None = Field(default=None, foreign_key="sprint.id")


class WorkItemLinkTable(WorkItemLink, table=True):
    __tablename__ = "work_item_link"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_workitem_id: UUID = Field(foreign_key="work_item.id")
    target_workitem_id: UUID = Field(foreign_key="work_item.id")


class RepositoryTable(Repository, table=True):
    __tablename__ = "repository"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)


class MergeRequestTable(MergeRequest, table=True):
    __tablename__ = "merge_request"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    repository_id: UUID = Field(foreign_key="repository.id")
    author_id: UUID = Field(foreign_key="user.id")


class ReviewTable(Review, table=True):
    __tablename__ = "review"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    mergerequest_id: UUID = Field(foreign_key="merge_request.id")
    reviewer_id: UUID = Field(foreign_key="user.id")


class CommentTable(Comment, table=True):
    __tablename__ = "comment"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    author_id: UUID = Field(foreign_key="user.id")


class TransitionTable(Transition, table=True):
    __tablename__ = "transition"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor_id: UUID | None = Field(default=None, foreign_key="user.id")


class TeamProfileTable(TeamProfile, table=True):
    __tablename__ = "team_profile"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    connection_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)
    scope_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)
    signal_config_group_ids: list[UUID] = Field(default_factory=list, sa_type=UUIDListJSON)
    code_connection_id: UUID | None = Field(default=None, foreign_key="source_connection.id")


class EvaluationWindowTable(EvaluationWindow, table=True):
    __tablename__ = "evaluation_window"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sprint_id: UUID | None = Field(default=None, foreign_key="sprint.id")
    sprint_label: str | None = Field(default=None)
    team_profile_id: UUID = Field(foreign_key="team_profile.id")


class ReportTable(Report, table=True):
    __tablename__ = "report"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    evaluation_window_id: UUID = Field(foreign_key="evaluation_window.id")


class SignalFindingTable(SignalFinding, table=True):
    __tablename__ = "signal_finding"
    __table_args__ = (UniqueConstraint("report_id", "signal_id", "entity_type", "entity_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    report_id: UUID = Field(foreign_key="report.id")


class ReportJobTable(SQLModel, table=True):
    __tablename__ = "report_job"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    team_profile_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(), ForeignKey("team_profile.id", ondelete="CASCADE"), nullable=False
        )
    )
    status: str  # queued | running | done | failed
    enqueued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    report_id: UUID | None = Field(
        default=None,
        sa_column=Column(sa.Uuid(), ForeignKey("report.id", ondelete="SET NULL"), nullable=True),
    )
    error: str | None = None


class TeamGitLabMemberTable(TeamGitLabMember, table=True):
    __tablename__ = "team_gitlab_member"
    __table_args__ = (UniqueConstraint("team_profile_id", "gitlab_user_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    team_profile_id: UUID = Field(foreign_key="team_profile.id")
    connection_id: UUID = Field(foreign_key="source_connection.id")
    is_available: bool = Field(default=True, sa_column_kwargs={"server_default": sa.true()})


class TeamGitLabRepositoryTable(TeamGitLabRepository, table=True):
    __tablename__ = "team_gitlab_repository"
    __table_args__ = (UniqueConstraint("team_profile_id", "gitlab_project_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    team_profile_id: UUID = Field(foreign_key="team_profile.id")
    connection_id: UUID = Field(foreign_key="source_connection.id")
    is_available: bool = Field(default=True, sa_column_kwargs={"server_default": sa.true()})


class AppSettingsTable(SQLModel, table=True):
    __tablename__ = "app_settings"

    id: int = Field(default=1, primary_key=True)
    telemetry_enabled: bool = Field(default=False)
    date_format: str = Field(default="dd/mm/yyyy")
