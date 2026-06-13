from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from em_radar_api.repositories import signal_pack_history as repo

_SAMPLE_YAML = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: test-pack
  version: 1.0.0
  description: Test pack for round-trip verification.
spec:
  signals:
    - id: stale-in-progress-work-item
      enabled: true
      params:
        days_threshold: 7
"""


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def test_round_trip_yields_byte_identical_yaml(session: Session) -> None:
    record = repo.append_pack(session, "test-pack", _SAMPLE_YAML)

    retrieved = repo.get_pack_yaml(session, record.id)

    assert retrieved == _SAMPLE_YAML


def test_list_history_returns_all_stored_packs(session: Session) -> None:
    repo.append_pack(session, "pack-a", _SAMPLE_YAML)
    repo.append_pack(session, "pack-b", _SAMPLE_YAML)

    history = repo.list_history(session)

    assert len(history) == 2
    assert {h.pack_name for h in history} == {"pack-a", "pack-b"}


def test_get_pack_yaml_returns_none_for_unknown_id(session: Session) -> None:
    assert repo.get_pack_yaml(session, uuid4()) is None
