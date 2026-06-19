from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from em_radar_api.signal_definitions import (
    SignalDefinitionCreate,
    SignalDefinitionRead,
    SignalDefinitionTable,
    SignalDefinitionUpdate,
)


class InvalidSignalDefinition(ValueError):
    pass


class DuplicateSignalName(ValueError):
    pass


def create_signal_definition(
    session: Session,
    definition: SignalDefinitionCreate,
) -> SignalDefinitionRead:
    _validate(definition.enabled, definition.target_scopes)
    row = SignalDefinitionTable.model_validate(definition.model_dump(mode="json"))
    _write(session, row)
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
) -> SignalDefinitionRead | None:
    row = session.get(SignalDefinitionTable, definition_id)
    if row is None:
        return None

    values = update.model_dump(mode="json", exclude_unset=True)
    enabled = values.get("enabled", row.enabled)
    target_scopes = values.get("target_scopes", row.target_scopes)
    _validate(enabled, target_scopes)
    row.sqlmodel_update(values)
    row.version += 1
    row.updated_at = datetime.now(UTC)
    _write(session, row)
    return SignalDefinitionRead.model_validate(row)


def delete_signal_definition(session: Session, definition_id: UUID) -> bool:
    row = session.get(SignalDefinitionTable, definition_id)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def _validate(enabled: bool, target_scopes: list[dict[str, str]]) -> None:
    if enabled and not target_scopes:
        raise InvalidSignalDefinition("enabled signals require at least one target scope")


def _write(session: Session, row: SignalDefinitionTable) -> None:
    try:
        session.add(row)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateSignalName("signal name must be unique") from error
    session.refresh(row)
