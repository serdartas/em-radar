from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

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
) -> PersistResult:
    """Upsert canonical entities and resolve cross-entity references.

    Entities are keyed by ``(source, external_id)`` so internal ids stay stable across
    fetches; rows without that natural key (reviews, transitions) keep their connector id.
    Re-running an identical fetch updates existing rows in place rather than duplicating them.
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
    plan: list[tuple[type[SQLModel], SQLModel, UUID]] = []
    counts: dict[str, int] = {}
    for table_cls, instances in groups:
        counts[table_cls.__tablename__] = len(instances)
        for instance in _parents_first(instances):
            internal_id = _internal_id(session, table_cls, instance)
            identity_map[instance.id] = internal_id
            plan.append((table_cls, instance, internal_id))

    session.exec(text("PRAGMA defer_foreign_keys=ON"))
    for table_cls, instance, internal_id in plan:
        data = instance.model_dump()
        data["id"] = internal_id
        resolve_references(table_cls, data, identity_map)
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


def _internal_id(session: Session, table_cls: type[SQLModel], instance: SQLModel) -> UUID:
    source = getattr(instance, "source", None)
    external_id = getattr(instance, "external_id", None)
    if source is None or external_id is None:
        return instance.id

    existing = session.exec(
        select(table_cls).where(
            table_cls.source == source,
            table_cls.external_id == external_id,
        )
    ).first()
    return existing.id if existing is not None else uuid4()
