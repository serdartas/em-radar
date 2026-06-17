from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from em_radar_core.models import (
    Board,
    Comment,
    MergeRequest,
    Review,
    Sprint,
    Transition,
    WorkItem,
    WorkItemLink,
)

IdentityMap = Mapping[UUID, UUID]


@dataclass(frozen=True)
class ReferenceSpec:
    """Cross-entity reference fields on a canonical model.

    ``scalar`` fields hold a single ``UUID`` (or ``None``); ``collection`` fields hold a
    ``list[UUID]``. Both are resolved from connector-emitted ids to internal ids.
    """

    scalar: tuple[str, ...] = ()
    collection: tuple[str, ...] = ()


REFERENCE_FIELDS: dict[type, ReferenceSpec] = {
    Board: ReferenceSpec(scalar=("project_id",)),
    Sprint: ReferenceSpec(scalar=("board_id",)),
    WorkItem: ReferenceSpec(
        scalar=("project_id", "assignee_id", "reporter_id", "parent_id", "current_sprint_id"),
        collection=("sprint_ids",),
    ),
    WorkItemLink: ReferenceSpec(scalar=("source_workitem_id", "target_workitem_id")),
    MergeRequest: ReferenceSpec(
        scalar=("repository_id", "author_id"),
        collection=("linked_workitem_ids",),
    ),
    Review: ReferenceSpec(scalar=("mergerequest_id", "reviewer_id")),
    Comment: ReferenceSpec(scalar=("entity_id", "author_id")),
    Transition: ReferenceSpec(scalar=("entity_id", "actor_id")),
}


def reference_spec(model_cls: type) -> ReferenceSpec | None:
    for base in model_cls.__mro__:
        spec = REFERENCE_FIELDS.get(base)
        if spec is not None:
            return spec
    return None


def resolve_references(
    model_cls: type,
    data: dict[str, object],
    identity_map: IdentityMap,
) -> dict[str, object]:
    """Rewrite the reference fields of ``data`` in place using ``identity_map``.

    A reference whose value is absent from the map is left untouched, so a connector may
    emit references to entities that were not part of the current fetch without them being
    silently dropped.
    """
    spec = reference_spec(model_cls)
    if spec is None:
        return data

    for name in spec.scalar:
        value = data.get(name)
        if isinstance(value, UUID):
            data[name] = identity_map.get(value, value)

    for name in spec.collection:
        values = data.get(name)
        if isinstance(values, Sequence) and not isinstance(values, str | bytes):
            data[name] = [
                identity_map.get(item, item) if isinstance(item, UUID) else item for item in values
            ]

    return data
