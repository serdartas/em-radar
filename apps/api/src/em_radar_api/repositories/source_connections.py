from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import TypeVar, cast
from uuid import UUID

from pydantic import SecretStr
from sqlmodel import Session, select

from em_radar_api.connector_registry import get_connector_capabilities
from em_radar_api.scope_definitions import ScopeDefinitionTable
from em_radar_api.security import mask_secret
from em_radar_api.source_connections import (
    SourceConnectionCreate,
    SourceConnectionRead,
    SourceConnectionTable,
    SourceConnectionUpdate,
)
from em_radar_api.tables import TeamProfileTable
from em_radar_core.connectors import ConnectorBase

ConnectorT = TypeVar("ConnectorT", bound=ConnectorBase)
CREDENTIAL_FIELD_NAMES = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "clientsecret",
        "password",
        "privatetoken",
        "refreshtoken",
        "secret",
        "token",
    }
)
SECRET_MARKER = "__em_radar_secret__"


class SourceConnectionInUse(ValueError):
    pass


class SourceConnectionDuplicateName(ValueError):
    pass


class SourceConnectionInvalidName(ValueError):
    pass


def create_source_connection(
    session: Session, connection: SourceConnectionCreate
) -> SourceConnectionRead:
    if _name_taken(session, connection.name):
        raise SourceConnectionDuplicateName(
            f"a connection named '{connection.name}' already exists"
        )
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
    if "name" in values and values["name"] is None:
        raise SourceConnectionInvalidName("connection name cannot be set to null")
    if "name" in values and _name_taken(session, values["name"], exclude_id=connection_id):
        raise SourceConnectionDuplicateName(f"a connection named '{values['name']}' already exists")
    if "config" in values:
        stored_config = _stored_config(cast(Mapping[str, object], values["config"]))
        if values.get("connector_name", row.connector_name) == row.connector_name:
            values["config"] = {**row.config, **stored_config}
        else:
            values["config"] = stored_config
    new_connector_name = values.get("connector_name", row.connector_name)
    if new_connector_name != row.connector_name:
        if _referencing_scopes(session, connection_id):
            raise SourceConnectionInUse(
                "source connection connector_name cannot change while scopes reference it"
            )
        if _teams_using_as_code_source(session, connection_id):
            caps = get_connector_capabilities(str(new_connector_name))
            if caps is None or not caps.provides_mergerequests:
                raise SourceConnectionInUse(
                    "source connection connector_name cannot change to a non-MR-capable connector"
                    " while referenced as a team's code source"
                )
    row.sqlmodel_update(values)
    _write(session, row)
    return _masked_read(row)


def delete_source_connection(session: Session, connection_id: UUID) -> bool:
    row = session.get(SourceConnectionTable, connection_id)
    if row is None:
        return False
    if _referencing_scopes(session, connection_id):
        raise SourceConnectionInUse("source connection is referenced by a scope definition")
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


def _name_taken(session: Session, name: str, exclude_id: UUID | None = None) -> bool:
    query = select(SourceConnectionTable).where(SourceConnectionTable.name == name)
    if exclude_id is not None:
        query = query.where(SourceConnectionTable.id != exclude_id)
    return session.exec(query).first() is not None


def _referencing_teams(session: Session, connection_id: UUID) -> list[TeamProfileTable]:
    return [
        team
        for team in session.exec(select(TeamProfileTable)).all()
        if connection_id in team.connection_ids
    ]


def _teams_using_as_code_source(session: Session, connection_id: UUID) -> list[TeamProfileTable]:
    return session.exec(
        select(TeamProfileTable).where(TeamProfileTable.code_connection_id == connection_id)
    ).all()


def _referencing_scopes(session: Session, connection_id: UUID) -> list[ScopeDefinitionTable]:
    return session.exec(
        select(ScopeDefinitionTable).where(ScopeDefinitionTable.connection_id == connection_id)
    ).all()


def _masked_read(row: SourceConnectionTable) -> SourceConnectionRead:
    return SourceConnectionRead(
        id=row.id,
        name=row.name,
        connector_name=row.connector_name,
        config=cast(dict[str, object], _mask_value(row.config)),
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
        return mask_secret(value.get_secret_value())
    if isinstance(value, Mapping) and set(value) == {SECRET_MARKER}:
        return mask_secret(str(value[SECRET_MARKER]))
    if field_name is not None and is_credential_field_name(field_name):
        return mask_secret(str(value))
    if isinstance(value, Mapping):
        return {str(key): _mask_value(item, str(key)) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_mask_value(item, field_name) for item in value]
    return deepcopy(value)


def is_credential_field_name(field_name: str) -> bool:
    normalized = "".join(character for character in field_name.casefold() if character.isalnum())
    return (
        normalized in CREDENTIAL_FIELD_NAMES
        or normalized.endswith("token")
        or "secret" in normalized
    )
