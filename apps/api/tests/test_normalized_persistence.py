import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from em_radar_connector_demo import (
    DEMO_MERGEREQUEST_COUNT,
    DEMO_USER_COUNT,
    DEMO_WORKITEM_COUNT,
    FIXTURE_NOW,
    DemoConnector,
)
from em_radar_connector_demo.fixtures import stable_id
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, Session, select

from em_radar_api.db import create_db_engine, create_session_factory
from em_radar_api.repositories.canonical import PersistResult, persist_fetch
from em_radar_api.tables import MergeRequestTable, UserTable, WorkItemTable
from em_radar_core.connectors import MergeRequestScope, WorkItemScope
from em_radar_core.models import (
    Board,
    Comment,
    EvaluationWindow,
    MergeRequest,
    Project,
    Repository,
    Review,
    Sprint,
    Transition,
    User,
    WindowType,
    WorkItem,
)


@dataclass
class Fetched:
    users: Sequence[User]
    projects: Sequence[Project]
    boards: Sequence[Board]
    sprints: Sequence[Sprint]
    workitems: Sequence[WorkItem]
    repositories: Sequence[Repository]
    mergerequests: Sequence[MergeRequest]
    reviews: Sequence[Review]
    transitions: Sequence[Transition]
    comments: Sequence[Comment]


async def _collect[T](iterator: AsyncIterator[T]) -> list[T]:
    return [item async for item in iterator]


async def _fetch_all() -> Fetched:
    connector = DemoConnector({})
    try:
        users = await connector.list_users()
        projects = await connector.list_projects()
        boards = [
            board
            for project in projects
            for board in await connector.list_boards(project.external_id)
        ]
        sprints = [
            sprint for board in boards for sprint in await connector.list_sprints(board.external_id)
        ]
        repositories = await connector.list_repositories()
        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=FIXTURE_NOW - timedelta(days=400),
            end=FIXTURE_NOW,
            team_profile_id=stable_id("team", "demo"),
        )
        workitems = await _collect(
            connector.fetch_workitems(
                WorkItemScope(project_external_ids=[project.external_id for project in projects]),
                window,
            )
        )
        mergerequests = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(
                    repository_external_ids=[repo.external_id for repo in repositories],
                    include_closed_unmerged=True,
                ),
                window,
            )
        )
        reviews = await _collect(connector.fetch_reviews([mr.external_id for mr in mergerequests]))
        transitions = await _collect(
            connector.fetch_transitions("workitem", [wi.external_id for wi in workitems])
        )
        comments = [
            *await _collect(
                connector.fetch_comments("workitem", [wi.external_id for wi in workitems])
            ),
            *await _collect(
                connector.fetch_comments("mergerequest", [mr.external_id for mr in mergerequests])
            ),
        ]
    finally:
        await connector.close()

    return Fetched(
        users=users,
        projects=projects,
        boards=boards,
        sprints=sprints,
        workitems=workitems,
        repositories=repositories,
        mergerequests=mergerequests,
        reviews=reviews,
        transitions=transitions,
        comments=comments,
    )


def _persist(session: Session, fetched: Fetched) -> PersistResult:
    return persist_fetch(
        session,
        users=fetched.users,
        projects=fetched.projects,
        boards=fetched.boards,
        sprints=fetched.sprints,
        workitems=fetched.workitems,
        repositories=fetched.repositories,
        mergerequests=fetched.mergerequests,
        reviews=fetched.reviews,
        transitions=fetched.transitions,
        comments=fetched.comments,
    )


def _count(session: Session, table: type[SQLModel]) -> int:
    return session.exec(select(func.count()).select_from(table)).one()


def _work_item(session: Session, external_id: str) -> WorkItemTable:
    return session.exec(select(WorkItemTable).where(WorkItemTable.external_id == external_id)).one()


def _cache(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_db_engine(tmp_path / "cache.db")
    SQLModel.metadata.create_all(engine)
    return create_session_factory(engine)


def test_persisting_demo_twice_is_idempotent_and_keeps_internal_ids(tmp_path: Path) -> None:
    fetched = asyncio.run(_fetch_all())
    session_factory = _cache(tmp_path)

    with session_factory() as session:
        _persist(session, fetched)
        first_counts = {
            UserTable.__tablename__: _count(session, UserTable),
            WorkItemTable.__tablename__: _count(session, WorkItemTable),
            MergeRequestTable.__tablename__: _count(session, MergeRequestTable),
        }
        story_id = _work_item(session, "workitem-2").id

    assert first_counts == {
        "user": DEMO_USER_COUNT,
        "work_item": DEMO_WORKITEM_COUNT,
        "merge_request": DEMO_MERGEREQUEST_COUNT,
    }

    with session_factory() as session:
        _persist(session, fetched)
        assert _count(session, UserTable) == DEMO_USER_COUNT
        assert _count(session, WorkItemTable) == DEMO_WORKITEM_COUNT
        assert _count(session, MergeRequestTable) == DEMO_MERGEREQUEST_COUNT
        assert _work_item(session, "workitem-2").id == story_id


def test_internal_ids_replace_connector_ids_and_resolve_references(tmp_path: Path) -> None:
    fetched = asyncio.run(_fetch_all())
    session_factory = _cache(tmp_path)

    with session_factory() as session:
        result = _persist(session, fetched)

    connector_story_id = stable_id("workitem", "workitem-2")
    connector_epic_id = stable_id("workitem", "workitem-1")
    connector_reporter_id = stable_id("user", "user-1")

    with session_factory() as session:
        story = _work_item(session, "workitem-2")
        epic = _work_item(session, "workitem-1")
        reporter = session.exec(select(UserTable).where(UserTable.external_id == "user-1")).one()
        merge_request = session.exec(
            select(MergeRequestTable).where(MergeRequestTable.external_id == "mr-1")
        ).one()

    assert story.id != connector_story_id
    assert epic.id != connector_epic_id

    assert story.parent_id == epic.id
    assert story.parent_id != connector_epic_id

    assert story.reporter_id == reporter.id
    assert reporter.id != connector_reporter_id

    assert merge_request.linked_workitem_ids == [epic.id]
    assert connector_epic_id not in merge_request.linked_workitem_ids

    assert result.identity_map[connector_story_id] == story.id
    assert result.identity_map[connector_epic_id] == epic.id


def test_updated_fields_are_reflected_without_changing_identity(tmp_path: Path) -> None:
    fetched = asyncio.run(_fetch_all())
    session_factory = _cache(tmp_path)

    with session_factory() as session:
        _persist(session, fetched)
        original_id = _work_item(session, "workitem-2").id

    fetched.workitems = [
        item.model_copy(update={"title": "Re-titled demo item"})
        if item.external_id == "workitem-2"
        else item
        for item in fetched.workitems
    ]

    with session_factory() as session:
        _persist(session, fetched)
        refreshed = _work_item(session, "workitem-2")
        count = _count(session, WorkItemTable)

    assert refreshed.id == original_id
    assert refreshed.title == "Re-titled demo item"
    assert count == DEMO_WORKITEM_COUNT
