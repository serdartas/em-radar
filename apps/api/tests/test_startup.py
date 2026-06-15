from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, Session

from em_radar_api.db import create_db_engine, create_session_factory
from em_radar_api.main import create_app
from em_radar_api.repositories.signal_configs import list_signal_configs, upsert_signal_config
from em_radar_api.signal_configs import SignalConfigUpsert
from em_radar_config import load_signal_pack

DEFAULT_PACK_PATH = (
    Path(__file__).parents[3] / "packages" / "config" / "defaults" / "default-pack.yaml"
)
EDITED_SIGNAL_ID = "stale-in-progress-work-item"


def test_first_startup_seeds_signal_configs_matching_default_pack(tmp_path: Path) -> None:
    session_factory = _empty_session_factory(tmp_path)

    with TestClient(create_app(app_session_factory=session_factory)):
        pass

    with session_factory() as session:
        stored = list_signal_configs(session)

    pack = load_signal_pack(DEFAULT_PACK_PATH.read_text()).pack
    expected = {
        signal.id: {
            "enabled": signal.enabled,
            "severity_override": signal.severity,
            "params": signal.params,
        }
        for signal in pack.spec.signals
    }

    assert len(stored) == 13
    assert {
        config.signal_id: {
            "enabled": config.enabled,
            "severity_override": config.severity_override,
            "params": config.params,
        }
        for config in stored
    } == expected


def test_subsequent_startup_preserves_user_edit(tmp_path: Path) -> None:
    session_factory = _empty_session_factory(tmp_path)
    app = create_app(app_session_factory=session_factory)

    with TestClient(app):
        pass

    with session_factory() as session:
        upsert_signal_config(
            session,
            SignalConfigUpsert(
                signal_id=EDITED_SIGNAL_ID,
                enabled=False,
                params={"days_threshold": 2},
            ),
        )

    with TestClient(app):
        pass

    with session_factory() as session:
        stored = {config.signal_id: config for config in list_signal_configs(session)}

    assert len(stored) == 13
    assert not stored[EDITED_SIGNAL_ID].enabled
    assert stored[EDITED_SIGNAL_ID].params == {"days_threshold": 2, "exclude_labels": []}


def _empty_session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_db_engine(tmp_path / "startup-test.db")
    SQLModel.metadata.create_all(engine)
    return create_session_factory(engine)
