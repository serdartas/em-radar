# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import TypeVar, cast
from uuid import UUID

from pydantic import SecretStr
from sqlmodel import Session, select

from em_radar_api.connector_registry import get_connector_capabilities
from em_radar_api.repositories.canonical import delete_canonical_data_for_source
from em_radar_api.scope_definitions import ScopeDefinitionTable
from em_radar_api.security import mask_secret
from em_radar_api.source_connections import (
    ConnectorName,
    SourceConnectionCreate,
    SourceConnectionRead,
    SourceConnectionTable,
    SourceConnectionUpdate,
)
from em_radar_api.tables import TeamProfileTable
from em_radar_core.connectors import ConnectorBase
from em_radar_core.models import Source

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

_CONNECTOR_TO_SOURCE: dict[str, Source] = {
    ConnectorName.JIRA: Source.JIRA,
    ConnectorName.GITLAB: Source.GITLAB,
}


@dataclass(frozen=True)
class DependentTeam:
    id: UUID
    name: str


class SourceConnectionInUse(ValueError):
    def __init__(self, message: str, dependent_teams: list[DependentTeam] | None = None) -> None:
        super().__init__(message)
        self.dependent_teams: list[DependentTeam] = dependent_teams or []


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
        incoming = cast(Mapping[str, object], values["config"])
        processed = _stored_config(incoming)
        if values.get("connector_name", row.connector_name) == row.connector_name:
            values["config"] = _deep_merge_config(processed, dict(row.config))
        else:
            values["config"] = _drop_masked_credentials(processed)
    old_connector_name = row.connector_name
    new_connector_name = values.get("connector_name", row.connector_name)
    if new_connector_name != old_connector_name:
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
    session.add(row)

    # When the connector type changes to a different source, the old source's cached data
    # is no longer reachable via any connection after this update.  Clear it when this was
    # the last (or only) connection of the old type — same last-of-source guard as delete.
    # Both the row update and the cache cleanup commit together so either both succeed or
    # both roll back (atomicity).
    if new_connector_name != old_connector_name:
        old_source = _CONNECTOR_TO_SOURCE.get(str(old_connector_name))
        if old_source is not None:
            sibling_of_old_exists = (
                session.exec(
                    select(SourceConnectionTable).where(
                        SourceConnectionTable.connector_name == old_connector_name,
                        SourceConnectionTable.id != connection_id,
                    )
                ).first()
                is not None
            )
            if not sibling_of_old_exists:
                delete_canonical_data_for_source(session, old_source)

    session.commit()
    session.refresh(row)
    return _masked_read(row)


def delete_source_connection(
    session: Session,
    connection_id: UUID,
    *,
    force: bool = False,
) -> bool:
    """Delete a source connection and clean up associated data.

    Without ``force``, raises :exc:`SourceConnectionInUse` (with ``dependent_teams``
    populated) when any team's scope or code source still references this connection.

    With ``force=True``, team references are scrubbed before deletion:
    1. Scope definitions for this connection are deleted and removed from team scope_ids.
    2. The connection is removed from every team's ``connection_ids`` list and
       ``code_connection_id`` is cleared where it matches.

    In all cases (with or without ``force``), cached canonical data for the connector
    source type is deleted when this is the last remaining connection of that type —
    preserving the cache when a sibling connection of the same type still exists (flows §8).

    No outbound calls to source systems are made.
    """
    row = session.get(SourceConnectionTable, connection_id)
    if row is None:
        return False

    dependent_scopes = _referencing_scopes(session, connection_id)
    all_dependent = _all_dependent_teams(session, connection_id)

    if not force and (dependent_scopes or all_dependent):
        team_info = [DependentTeam(id=t.id, name=t.name) for t in all_dependent]
        if all_dependent:
            message = (
                "source connection is referenced by one or more teams;"
                " pass force=true to cascade-delete"
            )
        else:
            message = (
                "source connection has scope definitions that will be removed;"
                " pass force=true to proceed"
            )
        raise SourceConnectionInUse(message, dependent_teams=team_info)

    if force:
        # 1. Remove each scope for this connection from teams, then delete the scope.
        scope_ids_to_remove = {scope.id for scope in dependent_scopes}
        if scope_ids_to_remove:
            for team in session.exec(select(TeamProfileTable)).all():
                updated = [s for s in team.scope_ids if s not in scope_ids_to_remove]
                if len(updated) != len(team.scope_ids):
                    team.scope_ids = updated
                    session.add(team)
            for scope in dependent_scopes:
                session.delete(scope)

        # 2. Scrub this connection from team.connection_ids / code_connection_id.
        for team in session.exec(select(TeamProfileTable)).all():
            changed = False
            if connection_id in team.connection_ids:
                team.connection_ids = [c for c in team.connection_ids if c != connection_id]
                changed = True
            if team.code_connection_id == connection_id:
                team.code_connection_id = None
                changed = True
            if changed:
                session.add(team)

    # 3. Delete cached canonical data when this is the last connection of this source type.
    #    Sibling connections sharing the same connector type still need the shared cache.
    source = _CONNECTOR_TO_SOURCE.get(str(row.connector_name))
    if source is not None:
        sibling_exists = (
            session.exec(
                select(SourceConnectionTable).where(
                    SourceConnectionTable.connector_name == row.connector_name,
                    SourceConnectionTable.id != connection_id,
                )
            ).first()
            is not None
        )
        if not sibling_exists:
            delete_canonical_data_for_source(session, source)

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


def _teams_using_as_code_source(session: Session, connection_id: UUID) -> list[TeamProfileTable]:
    return session.exec(
        select(TeamProfileTable).where(TeamProfileTable.code_connection_id == connection_id)
    ).all()


def _referencing_scopes(session: Session, connection_id: UUID) -> list[ScopeDefinitionTable]:
    return session.exec(
        select(ScopeDefinitionTable).where(ScopeDefinitionTable.connection_id == connection_id)
    ).all()


def _all_dependent_teams(session: Session, connection_id: UUID) -> list[TeamProfileTable]:
    """Return every team that depends on this connection via any reference path."""
    scope_ids_for_conn = {
        scope.id
        for scope in session.exec(
            select(ScopeDefinitionTable).where(ScopeDefinitionTable.connection_id == connection_id)
        ).all()
    }
    return [
        team
        for team in session.exec(select(TeamProfileTable)).all()
        if (
            connection_id in team.connection_ids
            or team.code_connection_id == connection_id
            or bool(set(team.scope_ids) & scope_ids_for_conn)
        )
    ]


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


def _is_mask_sentinel(key: str, incoming: object, stored: object) -> bool:
    """Return True when incoming is a mask sentinel for an existing stored secret.

    Covers two cases:
    - A credential-named key (e.g. "token") whose incoming value starts with "****".
    - Any key whose stored value is a SECRET_MARKER dict (created via SecretStr) and the
      incoming value is a mask sentinel — the key name may not be credential-shaped.
    """
    if not (isinstance(incoming, str) and incoming.startswith("****")):
        return False
    if is_credential_field_name(key):
        return True
    return isinstance(stored, dict) and set(stored) == {SECRET_MARKER}


def _deep_merge_config(
    incoming: Mapping[str, object], stored: dict[str, object]
) -> dict[str, object]:
    """Recursively merge an incoming PATCH config with the stored config.

    - Dicts are merged recursively.
    - Lists are merged positionally (element-level for dict items, verbatim otherwise).
    - Mask sentinels for credential or SecretStr-marked fields are dropped.
    - Keys only in stored are retained; incoming non-sentinel values win.
    """
    result: dict[str, object] = dict(stored)
    for key, value in incoming.items():
        stored_value = stored.get(key)
        if isinstance(value, dict) and isinstance(stored_value, dict):
            result[key] = _deep_merge_config(value, cast(dict[str, object], stored_value))
        elif (
            isinstance(value, list)
            and isinstance(stored_value, list)
            and len(value) == len(stored_value)
        ):
            merged: list[object] = []
            for item, sv in zip(value, stored_value):
                if isinstance(item, dict) and isinstance(sv, dict):
                    merged.append(_deep_merge_config(item, cast(dict[str, object], sv)))
                else:
                    merged.append(item)
            result[key] = merged
        elif _is_mask_sentinel(key, value, stored_value):
            pass  # mask sentinel — preserve existing stored secret
        else:
            result[key] = value
    return result


def _drop_masked_credentials(config: Mapping[str, object]) -> dict[str, object]:
    """Remove credential keys whose value is a mask sentinel (used on full-replacement writes).

    Called when the connector type changes and the config is replaced wholesale. Non-credential
    keys and genuine new values pass through unchanged.
    """
    result: dict[str, object] = {}
    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = _drop_masked_credentials(value)
        elif isinstance(value, list):
            result[key] = [
                _drop_masked_credentials(cast(Mapping[str, object], item))
                if isinstance(item, dict)
                else item
                for item in value
            ]
        elif is_credential_field_name(key) and isinstance(value, str) and value.startswith("****"):
            pass  # mask sentinel — omit from the replacement config
        else:
            result[key] = value
    return result
