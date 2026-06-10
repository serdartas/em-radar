from datetime import datetime, timezone

from em_radar_core.models import (
    BoardType,
    CommonFields,
    Confidence,
    EntityType,
    LinkType,
    MergeRequestState,
    PipelineStatus,
    ReviewDecision,
    Severity,
    Source,
    SprintState,
    StatusCategory,
    WorkingMode,
    WorkItemType,
)


def values(enum_type: type) -> set[str]:
    return {member.value for member in enum_type}


def test_enum_member_sets_match_the_canonical_data_model() -> None:
    assert values(Source) == {"jira", "gitlab", "github", "linear", "demo"}
    assert values(WorkItemType) == {"epic", "story", "task", "bug", "subtask", "spike", "other"}
    assert values(StatusCategory) == {"todo", "in_progress", "done", "blocked"}
    assert values(MergeRequestState) == {"open", "draft", "merged", "closed"}
    assert values(PipelineStatus) == {"success", "failed", "running", "canceled", "skipped", "none"}
    assert values(Severity) == {"info", "warning", "critical"}
    assert values(Confidence) == {"high", "medium", "low"}
    assert values(WorkingMode) == {"scrum", "kanban"}
    assert values(SprintState) == {"future", "active", "closed"}
    assert values(BoardType) == {"scrum", "kanban", "other"}
    assert values(ReviewDecision) == {
        "approved",
        "changes_requested",
        "commented",
        "dismissed",
        "requested",
    }
    assert values(LinkType) == {
        "blocks",
        "is_blocked_by",
        "relates_to",
        "duplicates",
        "is_duplicated_by",
    }
    assert values(EntityType) == {"workitem", "mergerequest", "sprint", "repository"}


def test_common_fields_defaults() -> None:
    before = datetime.now(timezone.utc)
    first = CommonFields(source=Source.DEMO, external_id="first")
    second = CommonFields(source=Source.DEMO, external_id="second")
    after = datetime.now(timezone.utc)

    assert first.id != second.id
    assert first.source_metadata == {}
    assert first.source_metadata is not second.source_metadata
    assert before <= first.fetched_at <= after
    assert first.fetched_at.tzinfo is timezone.utc
    assert first.source_url is None
    assert first.created_at is None
    assert first.updated_at is None
