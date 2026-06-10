from enum import StrEnum


class Source(StrEnum):
    JIRA = "jira"
    GITLAB = "gitlab"
    GITHUB = "github"
    LINEAR = "linear"
    DEMO = "demo"


class WorkItemType(StrEnum):
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    BUG = "bug"
    SUBTASK = "subtask"
    SPIKE = "spike"
    OTHER = "other"


class StatusCategory(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class MergeRequestState(StrEnum):
    OPEN = "open"
    DRAFT = "draft"
    MERGED = "merged"
    CLOSED = "closed"


class PipelineStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
    CANCELED = "canceled"
    SKIPPED = "skipped"
    NONE = "none"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WorkingMode(StrEnum):
    SCRUM = "scrum"
    KANBAN = "kanban"


class SprintState(StrEnum):
    FUTURE = "future"
    ACTIVE = "active"
    CLOSED = "closed"


class BoardType(StrEnum):
    SCRUM = "scrum"
    KANBAN = "kanban"
    OTHER = "other"


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"
    REQUESTED = "requested"


class LinkType(StrEnum):
    BLOCKS = "blocks"
    IS_BLOCKED_BY = "is_blocked_by"
    RELATES_TO = "relates_to"
    DUPLICATES = "duplicates"
    IS_DUPLICATED_BY = "is_duplicated_by"


class EntityType(StrEnum):
    WORKITEM = "workitem"
    MERGEREQUEST = "mergerequest"
    SPRINT = "sprint"
    REPOSITORY = "repository"
