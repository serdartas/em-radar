from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import JSON

from em_radar_core.models import (
    Board,
    BoardType,
    LinkType,
    Project,
    Source,
    Sprint,
    SprintState,
    StatusCategory,
    User,
    WorkItem,
    WorkItemLink,
    WorkItemType,
)


def work_item(**overrides: object) -> WorkItem:
    values: dict[str, object] = {
        "source": Source.DEMO,
        "external_id": "item-1",
        "project_id": uuid4(),
        "key": "DEMO-1",
        "type": WorkItemType.STORY,
        "title": "A valid work item",
        "status": "In Progress",
        "status_category": StatusCategory.IN_PROGRESS,
    }
    values.update(overrides)
    return WorkItem(**values)


def test_valid_planning_entities_can_be_constructed() -> None:
    project_id = uuid4()
    board_id = uuid4()
    sprint_id = uuid4()

    user = User(source=Source.DEMO, external_id="user-1", display_name="Demo User")
    project = Project(source=Source.DEMO, external_id="project-1", key="DEMO", name="Demo")
    board = Board(
        source=Source.DEMO,
        external_id="board-1",
        project_id=project_id,
        name="Delivery",
        type=BoardType.SCRUM,
    )
    sprint = Sprint(
        source=Source.DEMO,
        external_id="sprint-1",
        board_id=board_id,
        name="Sprint 1",
        state=SprintState.ACTIVE,
    )
    item = work_item(
        project_id=project_id,
        sprint_ids=[sprint_id],
        current_sprint_id=sprint_id,
        labels=["backend"],
        components=["api"],
    )

    assert user.is_bot is False
    assert project.key == "DEMO"
    assert board.type is BoardType.SCRUM
    assert sprint.state is SprintState.ACTIVE
    assert item.current_sprint_id == sprint_id


def test_work_item_array_defaults_are_independent_json_fields() -> None:
    first = work_item(external_id="item-1", key="DEMO-1")
    second = work_item(external_id="item-2", key="DEMO-2")

    first.labels.append("backend")

    assert second.labels == []
    assert second.components == []
    assert second.sprint_ids == []
    for field_name in ("labels", "components", "sprint_ids"):
        assert WorkItem.model_fields[field_name].metadata[0].sa_type is JSON


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": UUID(int=1), "parent_id": UUID(int=1)},
        {"type": WorkItemType.EPIC, "parent_id": UUID(int=2)},
        {"current_sprint_id": UUID(int=3), "sprint_ids": []},
        {"status_category": StatusCategory.DONE, "resolved_at": None},
        {
            "status_category": StatusCategory.IN_PROGRESS,
            "resolved_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
        },
    ],
)
def test_work_item_invariant_violations_raise(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        work_item(**overrides)


def test_done_work_item_requires_and_accepts_resolved_at() -> None:
    resolved_at = datetime(2026, 6, 10, tzinfo=timezone.utc)

    item = work_item(status_category=StatusCategory.DONE, resolved_at=resolved_at)

    assert item.resolved_at == resolved_at


@pytest.mark.parametrize(
    ("link_type", "forward_type", "inverse_type", "reverse_direction"),
    [
        (LinkType.BLOCKS, LinkType.BLOCKS, LinkType.IS_BLOCKED_BY, False),
        (LinkType.IS_BLOCKED_BY, LinkType.BLOCKS, LinkType.IS_BLOCKED_BY, True),
        (LinkType.DUPLICATES, LinkType.DUPLICATES, LinkType.IS_DUPLICATED_BY, False),
        (LinkType.IS_DUPLICATED_BY, LinkType.DUPLICATES, LinkType.IS_DUPLICATED_BY, True),
    ],
)
def test_asymmetric_work_item_links_are_created_as_canonical_pairs(
    link_type: LinkType,
    forward_type: LinkType,
    inverse_type: LinkType,
    reverse_direction: bool,
) -> None:
    source_id = uuid4()
    target_id = uuid4()

    forward, inverse = WorkItemLink.canonical_pair(source_id, target_id, link_type)

    if reverse_direction:
        source_id, target_id = target_id, source_id

    assert (forward.source_workitem_id, forward.target_workitem_id, forward.link_type) == (
        source_id,
        target_id,
        forward_type,
    )
    assert (inverse.source_workitem_id, inverse.target_workitem_id, inverse.link_type) == (
        target_id,
        source_id,
        inverse_type,
    )


def test_symmetric_link_type_cannot_be_created_as_an_asymmetric_pair() -> None:
    with pytest.raises(ValueError, match="not an asymmetric link type"):
        WorkItemLink.canonical_pair(uuid4(), uuid4(), LinkType.RELATES_TO)
