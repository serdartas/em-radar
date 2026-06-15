from pathlib import Path

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_api.signal_configs import SignalConfigTable
from em_radar_config import load_signal_pack

DEFAULT_PACK_PATH = (
    Path(__file__).parents[4] / "packages" / "config" / "defaults" / "default-pack.yaml"
)


def seed_default_signal_configs(app_session_factory: sessionmaker[Session]) -> None:
    with app_session_factory() as session:
        if session.exec(select(SignalConfigTable.id).limit(1)).first() is not None:
            return

        pack = load_signal_pack(DEFAULT_PACK_PATH.read_text()).pack
        default_severity = (
            pack.spec.defaults.severity_override if pack.spec.defaults is not None else None
        )
        session.add_all(
            [
                SignalConfigTable(
                    signal_id=signal.id,
                    enabled=signal.enabled,
                    severity_override=signal.severity or default_severity,
                    params=signal.params or {},
                )
                for signal in pack.spec.signals
            ]
        )
        session.commit()
