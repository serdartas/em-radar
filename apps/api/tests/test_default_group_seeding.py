from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, Session, select

from em_radar_api.db import create_db_engine, create_session_factory
from em_radar_api.main import create_app
from em_radar_api.signal_config_groups import SignalConfigGroupTable
from em_radar_api.signal_definitions import SignalDefinitionTable

DEFAULT_GROUP_NAME = "Default signals"
EXPECTED_SIGNAL_COUNT = 12  # 7 work-item + 5 merge-request


def test_first_startup_seeds_one_default_group_with_default_signals(tmp_path: Path) -> None:
    session_factory = _empty_session_factory(tmp_path)

    with TestClient(create_app(app_session_factory=session_factory)):
        pass

    with session_factory() as session:
        groups = session.exec(select(SignalConfigGroupTable)).all()
        definitions = session.exec(select(SignalDefinitionTable)).all()

    assert len(groups) == 1
    assert groups[0].name == DEFAULT_GROUP_NAME
    assert len(groups[0].signal_ids) == EXPECTED_SIGNAL_COUNT
    assert len(definitions) == EXPECTED_SIGNAL_COUNT


def test_second_startup_does_not_duplicate_the_default_group(tmp_path: Path) -> None:
    session_factory = _empty_session_factory(tmp_path)
    app = create_app(app_session_factory=session_factory)

    with TestClient(app):
        pass
    with TestClient(app):
        pass

    with session_factory() as session:
        groups = session.exec(select(SignalConfigGroupTable)).all()
        definitions = session.exec(select(SignalDefinitionTable)).all()

    assert len(groups) == 1
    assert len(definitions) == EXPECTED_SIGNAL_COUNT


def _empty_session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_db_engine(tmp_path / "seeding-test.db")
    SQLModel.metadata.create_all(engine)
    return create_session_factory(engine)
