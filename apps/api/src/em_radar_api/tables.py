from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

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

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    author_id: UUID = Field(foreign_key="user.id")


class TransitionTable(Transition, table=True):
    __tablename__ = "transition"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor_id: UUID | None = Field(default=None, foreign_key="user.id")


class TeamProfileTable(TeamProfile, table=True):
    __tablename__ = "team_profile"

    id: UUID = Field(default_factory=uuid4, primary_key=True)


class EvaluationWindowTable(EvaluationWindow, table=True):
    __tablename__ = "evaluation_window"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sprint_id: UUID | None = Field(default=None, foreign_key="sprint.id")
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
