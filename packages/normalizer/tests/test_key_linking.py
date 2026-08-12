from datetime import datetime, timezone
from uuid import uuid4

from em_radar_core.models import (
    MergeRequest,
    MergeRequestState,
    Source,
    StatusCategory,
    WorkItem,
    WorkItemType,
)
from em_radar_normalizer import (
    DEFAULT_WORKITEM_KEY_PATTERN,
    extract_workitem_keys,
    index_workitems_by_key,
    link_merge_request,
    resolve_workitem_ids,
)


def make_workitem(key: str) -> WorkItem:
    return WorkItem(
        source=Source.JIRA,
        external_id=key,
        project_id=uuid4(),
        key=key,
        type=WorkItemType.STORY,
        title=f"Work item {key}",
        status="To Do",
        status_category=StatusCategory.TODO,
    )


def make_merge_request(
    title: str = "",
    description: str | None = None,
    source_branch: str = "feature/misc",
) -> MergeRequest:
    return MergeRequest(
        source=Source.GITLAB,
        external_id="mr-1",
        repository_id=uuid4(),
        iid=1,
        title=title,
        description=description,
        state=MergeRequestState.OPEN,
        author_id=uuid4(),
        target_branch="main",
        source_branch=source_branch,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_extract_from_title() -> None:
    assert extract_workitem_keys("Fixes ABC-123 and DEF-4", None, "feature/misc") == [
        "ABC-123",
        "DEF-4",
    ]


def test_extract_from_description() -> None:
    assert extract_workitem_keys("no key here", "Relates to XYZ-9", "feature/misc") == ["XYZ-9"]


def test_extract_from_source_branch() -> None:
    assert extract_workitem_keys("no key", None, "feature/ABC-123-do-thing") == ["ABC-123"]


def test_multiple_keys_captured_across_fields() -> None:
    assert extract_workitem_keys(
        "ABC-1 in title",
        "DEF-2 in description",
        "feature/GHI-3-branch",
    ) == ["ABC-1", "DEF-2", "GHI-3"]


def test_deduplicates_repeated_keys_preserving_first_seen_order() -> None:
    assert extract_workitem_keys(
        "ABC-1 and ABC-1 again",
        "ABC-1 once more, plus DEF-2",
        "feature/ABC-1-work",
    ) == ["ABC-1", "DEF-2"]


def test_none_and_empty_description_handled() -> None:
    assert extract_workitem_keys("ABC-1", None, "feature/misc") == ["ABC-1"]
    assert extract_workitem_keys("ABC-1", "", "feature/misc") == ["ABC-1"]


def test_no_keys_returns_empty_list() -> None:
    assert extract_workitem_keys("no keys", "still nothing", "feature/misc") == []


def test_partial_tokens_are_not_matched() -> None:
    assert extract_workitem_keys("lowercase abc-1 and ABC1", None, "feature/misc") == []


def test_custom_pattern_is_respected() -> None:
    assert extract_workitem_keys("PROJ_42 here", None, "feature/misc", pattern=r"[A-Z]+_\d+") == [
        "PROJ_42"
    ]


def test_default_pattern_constant() -> None:
    assert DEFAULT_WORKITEM_KEY_PATTERN == r"[A-Z]+-\d+"


def test_resolve_to_ids_when_workitem_exists() -> None:
    abc = make_workitem("ABC-1")
    defg = make_workitem("DEF-2")
    index = index_workitems_by_key([abc, defg])

    assert resolve_workitem_ids(["ABC-1", "DEF-2"], index) == [abc.id, defg.id]


def test_keys_without_match_left_unresolved() -> None:
    abc = make_workitem("ABC-1")
    index = index_workitems_by_key([abc])

    assert resolve_workitem_ids(["ABC-1", "MISSING-9"], index) == [abc.id]


def test_resolution_preserves_key_order() -> None:
    abc = make_workitem("ABC-1")
    defg = make_workitem("DEF-2")
    index = index_workitems_by_key([abc, defg])

    assert resolve_workitem_ids(["DEF-2", "ABC-1"], index) == [defg.id, abc.id]


def test_link_merge_request_returns_keys_and_ids() -> None:
    abc = make_workitem("ABC-1")
    mr = make_merge_request(
        title="Implement ABC-1",
        description="Depends on MISSING-9",
        source_branch="feature/ABC-1-impl",
    )

    keys, ids = link_merge_request(mr, [abc])

    assert keys == ["ABC-1", "MISSING-9"]
    assert ids == [abc.id]
    assert mr.linked_workitem_keys == []
    assert mr.linked_workitem_ids == []
