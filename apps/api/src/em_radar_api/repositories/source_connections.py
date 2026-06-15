from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import TypeVar, cast
from uuid import UUID

from pydantic import SecretStr
from sqlmodel import Session, select

from em_radar_api.source_connections import (
    SourceConnectionCreate,
    SourceConnectionRead,
    SourceConnectionTable,
    SourceConnectionUpdate,
)
from em_radar_api.tables import TeamProfileTable
from em_radar_core.connectors import ConnectorBase

ConnectorT = TypeVar("ConnectorT", bound=ConnectorBase)
CREDENTIAL_FIELD_NAMES = frozenset({"token", "password", "api_key", "secret", "authorization"})
SECRET_MARKER = "__em_radar_secret__"


class SourceConnectionInUse(ValueError):
    pass


def create_source_connection(
    session: Session, connection: SourceConnectionCreate
) -> SourceConnectionRead:
    row = SourceConnectionTable.model_validate(connection)
    row.config = _stored_config(row.config)
    _write(session, row)
    return _masked_read(row)


def list_source_connections(session: Session) -> list[SourceConnectionRead]:
    rows = session.exec(
        select(SourceConnectionTable).order_by(SourceConnectionTable.created_at)
    ).all()
    return [_masked_read(row) for row in rows]


def get_source_connection(session: Session, connection_id: UUID) -> SourceConnectionRead | None:
    row = session.get(SourceConnectionTable, connection_id)
    return _masked_read(row) if row is not None else None


def update_source_connection(
    session: Session, connection_id: UUID, update: SourceConnectionUpdate
) -> SourceConnectionRead | None:
    row = session.get(SourceConnectionTable, connection_id)
    if row is None:
        return None

    values = update.model_dump(exclude_unset=True)
    if "config" in values:
        stored_config = _stored_config(cast(Mapping[str, object], values["config"]))
        if values.get("connector_name", row.connector_name) == row.connector_name:
            values["config"] = {**row.config, **stored_config}
        else:
            values["config"] = stored_config
    candidate = SourceConnectionTable.model_validate(row, update=values)
    _validate_team_scopes(session, connection_id, candidate)
    row.sqlmodel_update(values)
    _write(session, row)
    return _masked_read(row)


def delete_source_connection(session: Session, connection_id: UUID) -> bool:
    row = session.get(SourceConnectionTable, connection_id)
    if row is None:
        return False
    if _referencing_teams(session, connection_id):
        raise SourceConnectionInUse("source connection is referenced by a team")
    session.delete(row)
    session.commit()
    return True


def instantiate_connector(
    session: Session,
    connection_id: UUID,
    connector_factory: Callable[[dict[str, object]], ConnectorT],
) -> ConnectorT | None:
    row = session.get(SourceConnectionTable, connection_id)
    if row is None:
        return None
    return connector_factory(_connector_config(row.config))


def _write(session: Session, row: SourceConnectionTable) -> None:
    session.add(row)
    session.commit()
    session.refresh(row)


def _validate_team_scopes(
    session: Session,
    connection_id: UUID,
    candidate: SourceConnectionTable,
) -> None:
    for team in _referencing_teams(session, connection_id):
        connections = [
            candidate
            if referenced_id == connection_id
            else session.get(SourceConnectionTable, referenced_id)
            for referenced_id in team.connection_ids
        ]
        scoped_ids = (
            ("project_ids", team.project_ids, "selected_project_ids"),
            ("board_ids", team.board_ids, "selected_board_ids"),
            ("repository_ids", team.repository_ids, "selected_repository_ids"),
        )
        for field_name, values, connection_field in scoped_ids:
            available = {
                item
                for connection in connections
                if connection is not None
                for item in getattr(connection, connection_field)
            }
            if not set(values).issubset(available):
                raise SourceConnectionInUse(
                    f"source connection update would invalidate team {field_name}"
                )


def _referencing_teams(session: Session, connection_id: UUID) -> list[TeamProfileTable]:
    return [
        team
        for team in session.exec(select(TeamProfileTable)).all()
        if connection_id in team.connection_ids
    ]


def _masked_read(row: SourceConnectionTable) -> SourceConnectionRead:
    return SourceConnectionRead(
        id=row.id,
        connector_name=row.connector_name,
        config=cast(dict[str, object], _mask_value(row.config)),
        selected_project_ids=row.selected_project_ids,
        selected_board_ids=row.selected_board_ids,
        selected_repository_ids=row.selected_repository_ids,
        created_at=row.created_at,
    )


def _stored_config(config: Mapping[str, object]) -> dict[str, object]:
    return cast(dict[str, object], _mark_secrets(dict(config)))


def _mark_secrets(value: object) -> object:
    if isinstance(value, SecretStr):
        return {SECRET_MARKER: value.get_secret_value()}
    if isinstance(value, Mapping):
        return {str(key): _mark_secrets(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_mark_secrets(item) for item in value]
    return value


def _connector_config(config: Mapping[str, object]) -> dict[str, object]:
    return cast(dict[str, object], _unwrap_marked_secrets(deepcopy(dict(config))))


def _unwrap_marked_secrets(value: object) -> object:
    if isinstance(value, Mapping):
        if set(value) == {SECRET_MARKER}:
            return value[SECRET_MARKER]
        return {str(key): _unwrap_marked_secrets(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_unwrap_marked_secrets(item) for item in value]
    return value


def _mask_value(value: object, field_name: str | None = None) -> object:
    if isinstance(value, SecretStr):
        return _mask_secret(value.get_secret_value())
    if isinstance(value, Mapping) and set(value) == {SECRET_MARKER}:
        return _mask_secret(str(value[SECRET_MARKER]))
    if field_name is not None and field_name.lower() in CREDENTIAL_FIELD_NAMES:
        return _mask_secret(str(value))
    if isinstance(value, Mapping):
        return {str(key): _mask_value(item, str(key)) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_mask_value(item) for item in value]
    return deepcopy(value)


def _mask_secret(secret: str) -> str:
    return f"****{secret[-4:]}"
