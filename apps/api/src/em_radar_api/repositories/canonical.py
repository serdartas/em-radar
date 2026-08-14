from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4, uuid5

from sqlalchemy import text
from sqlmodel import Session, SQLModel, select

from em_radar_normalizer import resolve_references

from em_radar_api.tables import (
    BoardTable,
    CommentTable,
    MergeRequestTable,
    ProjectTable,
    RepositoryTable,
    ReviewTable,
    SprintTable,
    TransitionTable,
    UserTable,
    WorkItemTable,
)
from em_radar_core.models import (
    Board,
    Comment,
    MergeRequest,
    Project,
    Repository,
    Review,
    Sprint,
    Transition,
    User,
    WorkItem,
)


@dataclass(frozen=True)
class PersistResult:
    """Outcome of a persistence pass.

    ``identity_map`` maps connector-emitted ids to the stable internal ids; ``counts`` is the
    number of rows merged per table name.
    """

    identity_map: dict[UUID, UUID]
    counts: dict[str, int]


def persist_fetch(
    session: Session,
    *,
    users: Sequence[User] = (),
    projects: Sequence[Project] = (),
    boards: Sequence[Board] = (),
    sprints: Sequence[Sprint] = (),
    workitems: Sequence[WorkItem] = (),
    repositories: Sequence[Repository] = (),
    mergerequests: Sequence[MergeRequest] = (),
    reviews: Sequence[Review] = (),
    transitions: Sequence[Transition] = (),
    comments: Sequence[Comment] = (),
    preserve_sprint_links: bool = False,
) -> PersistResult:
    """Upsert canonical entities and resolve cross-entity references.

    Entities are keyed by ``(source, external_id)`` so internal ids stay stable across
    fetches; append-only history rows without that natural key (reviews, transitions) are
    keyed by a deterministic identity derived from their resolved content, so idempotence
    does not rely on connectors emitting stable event ids. Re-running an identical fetch
    updates existing rows in place rather than duplicating them.

    ``preserve_sprint_links`` is set only when sprint metadata could not be fetched (a degraded
    date-range run): without a sprint identity map the incoming work-item sprint fields cannot
    be resolved, so rather than clobbering cached links this keeps an existing row's persisted
    ``current_sprint_id``/``sprint_ids`` and writes no unresolved connector ids for a new row.
    A healthy fetch that genuinely returns no sprints keeps this False and reconciles normally.
    """
    groups: tuple[tuple[type[SQLModel], Sequence[SQLModel]], ...] = (
        (UserTable, users),
        (ProjectTable, projects),
        (RepositoryTable, repositories),
        (BoardTable, boards),
        (SprintTable, sprints),
        (WorkItemTable, workitems),
        (MergeRequestTable, mergerequests),
        (ReviewTable, reviews),
        (TransitionTable, transitions),
        (CommentTable, comments),
    )

    identity_map: dict[UUID, UUID] = {}
    plan: list[tuple[type[SQLModel], SQLModel, UUID | None]] = []
    counts: dict[str, int] = {}
    for table_cls, instances in groups:
        counts[table_cls.__tablename__] = len(instances)
        for instance in _parents_first(instances):
            internal_id = _natural_key_id(session, table_cls, instance)
            if internal_id is not None:
                identity_map[instance.id] = internal_id
            plan.append((table_cls, instance, internal_id))

    persisted_ids = set(identity_map.values())
    session.exec(text("PRAGMA defer_foreign_keys=ON"))
    for table_cls, instance, internal_id in plan:
        data = instance.model_dump()
        resolve_references(table_cls, data, identity_map)
        _drop_dangling_references(table_cls, data, persisted_ids)
        row_id = internal_id if internal_id is not None else _history_id(table_cls, data)
        data["id"] = row_id
        if preserve_sprint_links and table_cls is WorkItemTable:
            _preserve_work_item_sprint_links(session, data, row_id)
        session.merge(table_cls(**data))
    session.commit()

    return PersistResult(identity_map=identity_map, counts=counts)


def _parents_first(instances: Sequence[SQLModel]) -> list[SQLModel]:
    """Order self-referential rows so a parent precedes its children (work-item epics)."""
    by_id = {instance.id: instance for instance in instances}
    ordered: list[SQLModel] = []
    seen: set[UUID] = set()

    def visit(instance: SQLModel) -> None:
        if instance.id in seen:
            return
        seen.add(instance.id)
        parent_id = getattr(instance, "parent_id", None)
        if parent_id is not None and parent_id in by_id:
            visit(by_id[parent_id])
        ordered.append(instance)

    for instance in instances:
        visit(instance)
    return ordered


def _drop_dangling_references(
    table_cls: type[SQLModel],
    data: dict[str, object],
    persisted_ids: set[UUID],
) -> None:
    """Null nullable foreign keys that point outside the persisted set.

    A fetch may reference entities it did not include — a sprint-scoped report yields a story
    whose parent epic is out of scope, for instance. Such a reference cannot satisfy its
    foreign key, so a nullable one is dropped rather than failing the whole transaction. The
    id scheme assigns fresh internal ids per entity, so a reference is resolvable only when its
    target is part of this fetch; required references (e.g. ``project_id``) are always present.
    """
    for column in table_cls.__table__.columns:
        if not column.foreign_keys or not column.nullable:
            continue
        value = data.get(column.name)
        if isinstance(value, UUID) and value not in persisted_ids:
            data[column.name] = None


def _preserve_work_item_sprint_links(
    session: Session, data: dict[str, object], row_id: UUID
) -> None:
    """Keep sprint links intact when sprint metadata is unavailable (degraded date-range run).

    A full-column ``session.merge`` would otherwise overwrite an existing row's resolved sprint
    fields with unresolved incoming values. An existing row keeps its persisted
    ``current_sprint_id``/``sprint_ids``; a new row is written without unresolvable connector
    ids (null ``current_sprint_id``, empty ``sprint_ids``).
    """
    existing = session.get(WorkItemTable, row_id)
    if existing is not None:
        data["current_sprint_id"] = existing.current_sprint_id
        data["sprint_ids"] = list(existing.sprint_ids)
    else:
        data["current_sprint_id"] = None
        data["sprint_ids"] = []


def _natural_key_id(session: Session, table_cls: type[SQLModel], instance: SQLModel) -> UUID | None:
    """Stable internal id for an entity keyed by ``(source, external_id)``.

    Returns ``None`` for append-only history rows that have no natural key; those are
    identified by :func:`_history_id` instead.
    """
    source = getattr(instance, "source", None)
    external_id = getattr(instance, "external_id", None)
    if source is None or external_id is None:
        return None

    existing = session.exec(
        select(table_cls).where(
            table_cls.source == source,
            table_cls.external_id == external_id,
        )
    ).first()
    return existing.id if existing is not None else uuid4()


_HISTORY_NAMESPACE = UUID("ed0c5b9a-4a1d-5e2b-9c3f-0a1b2c3d4e5f")

_HISTORY_IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "review": ("mergerequest_id", "reviewer_id", "decision", "submitted_at"),
    "transition": (
        "entity_type",
        "entity_id",
        "from_status",
        "to_status",
        "actor_id",
        "occurred_at",
    ),
}


def _history_id(table_cls: type[SQLModel], data: dict[str, object]) -> UUID:
    """Deterministic id for an append-only history row.

    Derived from the row's resolved internal references and immutable event content so that
    re-fetching the same event maps to the same row, independent of any transient id the
    connector emitted. References are already resolved to internal ids when this is called,
    keeping the identity stable across fetches.
    """
    fields = _HISTORY_IDENTITY_FIELDS[table_cls.__tablename__]
    key = "|".join([table_cls.__tablename__, *(str(data.get(field)) for field in fields)])
    return uuid5(_HISTORY_NAMESPACE, key)
