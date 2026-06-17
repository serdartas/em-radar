from sqlmodel import Session, select

from em_radar_api.signal_configs import SignalConfigRead, SignalConfigTable, SignalConfigUpsert
from em_radar_config import SIGNAL_CATALOG, SignalCatalogEntry


def upsert_signal_config(
    session: Session,
    config: SignalConfigUpsert,
) -> SignalConfigRead:
    catalog_entry = _get_catalog_entry(config.signal_id)
    normalized_config = config.model_copy(
        update={
            "params": catalog_entry.params_schema.model_validate(config.params).model_dump(
                mode="json"
            )
        }
    )
    row = _get_row(session, config.signal_id)
    if row is None:
        row = SignalConfigTable.model_validate(normalized_config)
    else:
        row.sqlmodel_update(normalized_config.model_dump())
    _write(session, row)
    return SignalConfigRead.model_validate(row)


def list_signal_configs(session: Session) -> list[SignalConfigRead]:
    rows = session.exec(select(SignalConfigTable).order_by(SignalConfigTable.signal_id)).all()
    return [SignalConfigRead.model_validate(row) for row in rows]


def reset_signal_config(
    session: Session,
    signal_id: str,
) -> SignalConfigRead:
    catalog_entry = _get_catalog_entry(signal_id)
    row = _get_row(session, signal_id)
    defaults = SignalConfigUpsert(
        signal_id=signal_id,
        params=catalog_entry.params_schema().model_dump(mode="json"),
    )
    if row is None:
        row = SignalConfigTable.model_validate(defaults)
    else:
        row.sqlmodel_update(defaults.model_dump())
    _write(session, row)
    return SignalConfigRead.model_validate(row)


def reset_all_signal_configs(session: Session) -> list[SignalConfigRead]:
    for row in session.exec(select(SignalConfigTable)).all():
        catalog_entry = _get_catalog_entry(row.signal_id)
        defaults = SignalConfigUpsert(
            signal_id=row.signal_id,
            params=catalog_entry.params_schema().model_dump(mode="json"),
        )
        row.sqlmodel_update(defaults.model_dump())
        session.add(row)
    session.commit()
    return list_signal_configs(session)


def _get_row(session: Session, signal_id: str) -> SignalConfigTable | None:
    return session.exec(
        select(SignalConfigTable).where(SignalConfigTable.signal_id == signal_id)
    ).one_or_none()


def _get_catalog_entry(signal_id: str) -> SignalCatalogEntry:
    try:
        return SIGNAL_CATALOG[signal_id]
    except KeyError as error:
        raise ValueError(f"unknown signal id: {signal_id}") from error


def _write(session: Session, row: SignalConfigTable) -> None:
    session.add(row)
    session.commit()
    session.refresh(row)
