# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from em_radar_api.repositories.signal_config_groups import remove_signal_id_from_all_groups
from em_radar_api.signal_definitions import (
    SignalDefinitionCreate,
    SignalDefinitionRead,
    SignalDefinitionTable,
    SignalDefinitionUpdate,
)


class DuplicateSignalName(ValueError):
    pass


def create_signal_definition(
    session: Session,
    definition: SignalDefinitionCreate,
    *,
    commit: bool = True,
) -> SignalDefinitionRead:
    row = SignalDefinitionTable.model_validate(definition.model_dump(mode="json"))
    _write(session, row, commit=commit)
    return SignalDefinitionRead.model_validate(row)


def list_signal_definitions(session: Session) -> list[SignalDefinitionRead]:
    rows = session.exec(select(SignalDefinitionTable).order_by(SignalDefinitionTable.name)).all()
    return [SignalDefinitionRead.model_validate(row) for row in rows]


def get_signal_definition(
    session: Session,
    definition_id: UUID,
) -> SignalDefinitionRead | None:
    row = session.get(SignalDefinitionTable, definition_id)
    return SignalDefinitionRead.model_validate(row) if row is not None else None


def update_signal_definition(
    session: Session,
    definition_id: UUID,
    update: SignalDefinitionUpdate,
    *,
    commit: bool = True,
) -> SignalDefinitionRead | None:
    row = session.get(SignalDefinitionTable, definition_id)
    if row is None:
        return None

    values = update.model_dump(mode="json", exclude_unset=True)
    row.sqlmodel_update(values)
    row.updated_at = datetime.now(UTC)
    _write(session, row, commit=commit)
    return SignalDefinitionRead.model_validate(row)


def delete_signal_definition(session: Session, definition_id: UUID) -> bool:
    row = session.get(SignalDefinitionTable, definition_id)
    if row is None:
        return False
    remove_signal_id_from_all_groups(session, definition_id)
    session.delete(row)
    session.commit()
    return True


def _write(session: Session, row: SignalDefinitionTable, *, commit: bool) -> None:
    try:
        session.add(row)
        if commit:
            session.commit()
        else:
            session.flush()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateSignalName("signal name must be unique") from error
    if commit:
        session.refresh(row)
