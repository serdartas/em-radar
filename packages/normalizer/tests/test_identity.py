from uuid import uuid4

from em_radar_core.models import EntityType, MergeRequestState, Source, StatusCategory, WorkItem
from em_radar_normalizer import reference_spec, resolve_references


def test_resolve_references_remaps_scalar_and_collection_fields() -> None:
    connector_project = uuid4()
    connector_assignee = uuid4()
    connector_parent = uuid4()
    connector_sprint = uuid4()
    internal_project = uuid4()
    internal_assignee = uuid4()
    internal_parent = uuid4()
    internal_sprint = uuid4()
    identity_map = {
        connector_project: internal_project,
        connector_assignee: internal_assignee,
        connector_parent: internal_parent,
        connector_sprint: internal_sprint,
    }

    data = {
        "project_id": connector_project,
        "assignee_id": connector_assignee,
        "reporter_id": None,
        "parent_id": connector_parent,
        "current_sprint_id": connector_sprint,
        "sprint_ids": [connector_sprint],
    }

    resolved = resolve_references(WorkItem, data, identity_map)

    assert resolved["project_id"] == internal_project
    assert resolved["assignee_id"] == internal_assignee
    assert resolved["reporter_id"] is None
    assert resolved["parent_id"] == internal_parent
    assert resolved["current_sprint_id"] == internal_sprint
    assert resolved["sprint_ids"] == [internal_sprint]


def test_resolve_references_leaves_unmapped_values_untouched() -> None:
    unmapped = uuid4()
    data = {"project_id": unmapped, "assignee_id": None, "sprint_ids": [unmapped]}

    resolved = resolve_references(WorkItem, data, {})

    assert resolved["project_id"] == unmapped
    assert resolved["sprint_ids"] == [unmapped]


def test_reference_spec_resolves_subclasses_and_unknown_models() -> None:
    class WorkItemSubclass(WorkItem):
        pass

    assert reference_spec(WorkItemSubclass) is reference_spec(WorkItem)
    assert reference_spec(int) is None


def test_polymorphic_entity_id_is_resolved() -> None:
    connector_entity = uuid4()
    internal_entity = uuid4()
    data = {
        "entity_type": EntityType.WORKITEM,
        "entity_id": connector_entity,
        "actor_id": None,
    }

    from em_radar_core.models import Transition

    resolved = resolve_references(Transition, data, {connector_entity: internal_entity})

    assert resolved["entity_id"] == internal_entity


def test_enums_are_not_treated_as_references() -> None:
    from em_radar_core.models import MergeRequest

    data = {
        "repository_id": uuid4(),
        "author_id": uuid4(),
        "state": MergeRequestState.OPEN,
        "linked_workitem_ids": [],
        "linked_workitem_keys": ["ABC-1"],
    }
    original_state = data["state"]

    resolved = resolve_references(MergeRequest, data, {})

    assert resolved["state"] is original_state
    assert resolved["linked_workitem_keys"] == ["ABC-1"]
    assert Source.DEMO not in resolved.values()
    assert StatusCategory.DONE not in resolved.values()
