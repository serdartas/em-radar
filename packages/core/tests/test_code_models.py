from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import JSON

from em_radar_core.models import (
    Comment,
    EntityType,
    MergeRequest,
    MergeRequestState,
    PipelineStatus,
    Repository,
    Review,
    ReviewDecision,
    Source,
    StatusCategory,
    Transition,
)


NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def merge_request(**overrides: object) -> MergeRequest:
    values: dict[str, object] = {
        "source": Source.DEMO,
        "external_id": "mr-1",
        "repository_id": uuid4(),
        "iid": 1,
        "title": "A valid merge request",
        "state": MergeRequestState.OPEN,
        "author_id": uuid4(),
        "target_branch": "main",
        "source_branch": "feature/DEMO-1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return MergeRequest(**values)


def test_valid_code_entities_can_be_constructed() -> None:
    repository = Repository(
        source=Source.DEMO,
        external_id="repo-1",
        name="em-radar",
        full_path="engineering/em-radar",
        default_branch="main",
    )
    mr = merge_request(
        pipeline_status=PipelineStatus.SUCCESS,
        linked_workitem_keys=["DEMO-1"],
        linked_workitem_ids=[uuid4()],
    )
    review = Review(
        mergerequest_id=mr.id,
        reviewer_id=uuid4(),
        decision=ReviewDecision.REQUESTED,
    )
    comment = Comment(
        source=Source.DEMO,
        external_id="comment-1",
        entity_type=EntityType.MERGEREQUEST,
        entity_id=mr.id,
        author_id=uuid4(),
        created_at=NOW,
    )
    transition = Transition(
        entity_type=EntityType.WORKITEM,
        entity_id=uuid4(),
        to_status="In Progress",
        to_status_category=StatusCategory.IN_PROGRESS,
        occurred_at=NOW,
    )

    assert repository.is_archived is False
    assert mr.pipeline_status is PipelineStatus.SUCCESS
    assert review.submitted_at is None
    assert comment.is_system is False
    assert transition.from_status is None
    assert transition.actor_id is None


def test_merge_request_array_defaults_are_independent_json_fields() -> None:
    first = merge_request(external_id="mr-1", iid=1)
    second = merge_request(external_id="mr-2", iid=2)

    first.linked_workitem_keys.append("DEMO-1")

    assert second.linked_workitem_keys == []
    assert second.linked_workitem_ids == []
    for field_name in ("linked_workitem_keys", "linked_workitem_ids"):
        assert MergeRequest.model_fields[field_name].metadata[0].sa_type is JSON


@pytest.mark.parametrize("field_name", ["created_at", "updated_at"])
def test_merge_request_requires_created_and_updated_timestamps(field_name: str) -> None:
    values: dict[str, object] = {
        "source": Source.DEMO,
        "external_id": "mr-1",
        "repository_id": uuid4(),
        "iid": 1,
        "title": "Missing timestamp",
        "state": MergeRequestState.OPEN,
        "author_id": uuid4(),
        "target_branch": "main",
        "source_branch": "feature",
        "created_at": NOW,
        "updated_at": NOW,
    }
    del values[field_name]

    with pytest.raises(ValidationError):
        MergeRequest(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": MergeRequestState.MERGED},
        {"state": MergeRequestState.CLOSED},
        {"merged_at": NOW, "closed_at": NOW},
    ],
)
def test_merge_request_invariant_violations_raise(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        merge_request(**overrides)


def test_merged_and_closed_merge_requests_accept_required_timestamp() -> None:
    merged = merge_request(state=MergeRequestState.MERGED, merged_at=NOW)
    closed = merge_request(state=MergeRequestState.CLOSED, closed_at=NOW)

    assert merged.merged_at == NOW
    assert closed.closed_at == NOW


@pytest.mark.parametrize("model_type", [Comment, Transition])
@pytest.mark.parametrize("entity_type", [EntityType.SPRINT, EntityType.REPOSITORY])
def test_history_entities_only_reference_supported_parent_types(
    model_type: type[Comment] | type[Transition],
    entity_type: EntityType,
) -> None:
    common: dict[str, object] = {
        "entity_type": entity_type,
        "entity_id": UUID(int=1),
    }
    values = (
        {
            **common,
            "source": Source.DEMO,
            "external_id": "comment-1",
            "author_id": UUID(int=2),
            "created_at": NOW,
        }
        if model_type is Comment
        else {
            **common,
            "to_status": "Done",
            "to_status_category": StatusCategory.DONE,
            "occurred_at": NOW,
        }
    )

    with pytest.raises(ValidationError):
        model_type(**values)
