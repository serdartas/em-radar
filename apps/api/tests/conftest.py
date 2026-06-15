from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import em_radar_api.tables  # noqa: F401  (register table metadata for create_all)
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

from em_radar_api.db import (
    create_db_engine,
    create_session_factory,
    get_session,
    get_write_session,
)
from em_radar_api.main import app


@pytest.fixture
def api_harness(tmp_path: Path) -> Iterator[SimpleNamespace]:
    engine = create_db_engine(tmp_path / "api-test.db")
    SQLModel.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    def _session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_write_session] = _session
    try:
        yield SimpleNamespace(
            client=TestClient(app),
            session_factory=session_factory,
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def api_client(api_harness: SimpleNamespace) -> TestClient:
    return api_harness.client


@pytest.fixture
def session_factory(api_harness: SimpleNamespace) -> sessionmaker[Session]:
    return api_harness.session_factory
