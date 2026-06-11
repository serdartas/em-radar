from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import JSON, text
from sqlmodel import Field, SQLModel, select

from em_radar_api.db import (
    DATABASE_PATH_ENV,
    create_db_engine,
    create_session_factory,
    schema_version,
)
from em_radar_core.models import Project, Source


class PersistedProject(Project, table=True):
    __tablename__ = "project"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_metadata: dict[str, object] | None = Field(default_factory=dict, sa_type=JSON)


def test_file_backed_sqlite_session_round_trips_canonical_row(tmp_path: Path) -> None:
    database_path = tmp_path / "em-radar.db"
    engine = create_db_engine(database_path)
    session_factory = create_session_factory(engine)
    SQLModel.metadata.create_all(engine)

    project = PersistedProject(
        source=Source.DEMO,
        external_id="demo-project",
        key="DEMO",
        name="Demo Project",
    )
    with session_factory() as session:
        session.add(project)
        session.commit()

    with session_factory() as session:
        stored_project = session.exec(select(PersistedProject)).one()
        journal_mode = session.exec(text("PRAGMA journal_mode")).one()[0]
        foreign_keys = session.exec(text("PRAGMA foreign_keys")).one()[0]

    assert database_path.is_file()
    assert stored_project.key == "DEMO"
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
