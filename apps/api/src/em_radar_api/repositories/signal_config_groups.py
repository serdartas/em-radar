from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from em_radar_api.signal_config_groups import (
    SignalConfigGroupCreate,
    SignalConfigGroupRead,
    SignalConfigGroupTable,
    SignalConfigGroupUpdate,
)
from em_radar_api.signal_definitions import SignalDefinitionTable


class DuplicateGroupName(ValueError):
    pass


class InvalidSignalConfigGroup(ValueError):
    pass


def create_signal_config_group(
    session: Session,
    group: SignalConfigGroupCreate,
) -> SignalConfigGroupRead:
    _validate_signal_ids(session, group.signal_ids)
    now = datetime.now(UTC)
    row = SignalConfigGroupTable.model_validate(
        group, update={"created_at": now, "updated_at": now}
    )
    _write(session, row)
    return SignalConfigGroupRead.model_validate(row)


def list_signal_config_groups(session: Session) -> list[SignalConfigGroupRead]:
    rows = session.exec(select(SignalConfigGroupTable).order_by(SignalConfigGroupTable.name)).all()
    return [SignalConfigGroupRead.model_validate(row) for row in rows]


def get_signal_config_group(
    session: Session,
    group_id: UUID,
) -> SignalConfigGroupRead | None:
    row = session.get(SignalConfigGroupTable, group_id)
    return SignalConfigGroupRead.model_validate(row) if row is not None else None


def update_signal_config_group(
    session: Session,
    group_id: UUID,
    update: SignalConfigGroupUpdate,
) -> SignalConfigGroupRead | None:
    row = session.get(SignalConfigGroupTable, group_id)
    if row is None:
        return None

    values = update.model_dump(exclude_unset=True)
    if "name" in values and values["name"] is None:
        raise InvalidSignalConfigGroup("name cannot be null")
    if "signal_ids" in values:
        if values["signal_ids"] is None:
            raise InvalidSignalConfigGroup("signal_ids cannot be null")
        _validate_signal_ids(session, values["signal_ids"])
    row.sqlmodel_update(values)
    row.updated_at = datetime.now(UTC)
    _write(session, row)
    return SignalConfigGroupRead.model_validate(row)


def delete_signal_config_group(session: Session, group_id: UUID) -> bool:
    row = session.get(SignalConfigGroupTable, group_id)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def _validate_signal_ids(session: Session, signal_ids: list[UUID]) -> None:
    if not signal_ids:
        return
    if len(set(signal_ids)) != len(signal_ids):
        raise InvalidSignalConfigGroup("signal_ids must not contain duplicates")
    found = session.exec(
        select(SignalDefinitionTable).where(SignalDefinitionTable.id.in_(signal_ids))
    ).all()
    if len(found) != len(signal_ids):
        raise InvalidSignalConfigGroup("signal_ids must reference existing signal definitions")


def _write(session: Session, row: SignalConfigGroupTable) -> None:
    try:
        session.add(row)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateGroupName("group name must be unique") from error
    session.refresh(row)
