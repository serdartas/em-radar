from uuid import UUID

from sqlmodel import Session, select

from em_radar_api.models.signal_pack_history import SignalPackHistory


def append_pack(session: Session, pack_name: str, raw_yaml: str) -> SignalPackHistory:
    record = SignalPackHistory(pack_name=pack_name, raw_yaml=raw_yaml)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_history(session: Session) -> list[SignalPackHistory]:
    return list(session.exec(select(SignalPackHistory)))


def get_pack_yaml(session: Session, pack_id: UUID) -> str | None:
    record = session.get(SignalPackHistory, pack_id)
    return record.raw_yaml if record else None
