from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy.exc
from sqlalchemy import text
from sqlmodel import SQLModel, select

from em_radar_api.db import (
    DATABASE_PATH_ENV,
    create_db_engine,
    create_session_factory,
    schema_version,
)
from em_radar_api.tables import CommentTable, ProjectTable, UserTable
from em_radar_core.models import EntityType, Source


def test_file_backed_sqlite_session_round_trips_canonical_row(tmp_path: Path) -> None:
    database_path = tmp_path / "em-radar.db"
    engine = create_db_engine(database_path)
    session_factory = create_session_factory(engine)
    SQLModel.metadata.create_all(engine)

    project = ProjectTable(
        source=Source.JIRA,
        external_id="jira-project",
        key="PROJ",
        name="Test Project",
    )
    with session_factory() as session:
        session.add(project)
        session.commit()

    with session_factory() as session:
        stored_project = session.exec(select(ProjectTable)).one()
        journal_mode = session.exec(text("PRAGMA journal_mode")).one()[0]
        foreign_keys = session.exec(text("PRAGMA foreign_keys")).one()[0]

    assert database_path.is_file()
    assert stored_project.key == "PROJ"
    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert schema_version == 1


def test_database_path_is_configurable_by_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "configured.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))

    engine = create_db_engine()

    assert engine.url.database == str(database_path)


def test_comment_source_external_id_unique_constraint(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "comment-constraint-test.db")
    SQLModel.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    user = UserTable(
        source=Source.JIRA,
        external_id="u-1",
        display_name="Alice",
        is_bot=False,
        fetched_at=datetime(2026, 1, 1),
    )
    with session_factory() as session:
        session.add(user)
        session.commit()
        session.refresh(user)

    shared_kwargs = {
        "source": Source.JIRA,
        "external_id": "comment-42",
        "entity_type": EntityType.WORKITEM,
        "entity_id": uuid4(),
        "author_id": user.id,
        "created_at": datetime(2026, 1, 1),
    }

    with session_factory() as session:
        session.add(CommentTable(**shared_kwargs))
        session.commit()

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        with session_factory() as session:
            session.add(CommentTable(**shared_kwargs))
            session.commit()
