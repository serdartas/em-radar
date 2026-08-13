from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, Session, select

from em_radar_api.db import create_db_engine, create_session_factory
from em_radar_api.main import create_app
from em_radar_api.signal_definitions import SignalDefinitionTable


def test_first_startup_seeds_default_signal_group(tmp_path: Path) -> None:
    """Startup seeds the default signal group with 13 declarative signals (8 WI + 5 MR)."""
    session_factory = _empty_session_factory(tmp_path)

    with TestClient(create_app(app_session_factory=session_factory)):
        pass

    with session_factory() as session:
        count = session.exec(select(SignalDefinitionTable)).all()

    assert len(count) == 13


def test_subsequent_startup_does_not_duplicate_signals(tmp_path: Path) -> None:
    session_factory = _empty_session_factory(tmp_path)
    app = create_app(app_session_factory=session_factory)

    with TestClient(app):
        pass

    with TestClient(app):
        pass

    with session_factory() as session:
        count = session.exec(select(SignalDefinitionTable)).all()

    assert len(count) == 13


def _empty_session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_db_engine(tmp_path / "startup-test.db")
    SQLModel.metadata.create_all(engine)
    return create_session_factory(engine)
