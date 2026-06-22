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
from em_radar_api.tables import TeamProfileTable


class DuplicateGroupName(ValueError):
    pass


class InvalidSignalConfigGroup(ValueError):
    pass


class SignalConfigGroupInUse(ValueError):
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


def remove_signal_id_from_all_groups(session: Session, signal_id: UUID) -> None:
    rows = session.exec(select(SignalConfigGroupTable)).all()
    for row in rows:
        if signal_id in row.signal_ids:
            row.signal_ids = [sid for sid in row.signal_ids if sid != signal_id]
            row.updated_at = datetime.now(UTC)
            session.add(row)


def delete_signal_config_group(session: Session, group_id: UUID) -> bool:
    row = session.get(SignalConfigGroupTable, group_id)
    if row is None:
        return False
    if _referencing_teams(session, group_id):
        raise SignalConfigGroupInUse("signal config group is referenced by a team")
    session.delete(row)
    session.commit()
    return True


def _referencing_teams(session: Session, group_id: UUID) -> list[TeamProfileTable]:
    return [
        team
        for team in session.exec(select(TeamProfileTable)).all()
        if group_id in team.signal_config_group_ids
    ]


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
