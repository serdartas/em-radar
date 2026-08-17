# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session, select

from em_radar_api.repositories.source_connections import is_credential_field_name
from em_radar_api.scope_definitions import (
    ScopeDefinitionCreate,
    ScopeDefinitionRead,
    ScopeDefinitionTable,
    ScopeDefinitionUpdate,
    ScopeType,
)
from em_radar_api.source_connections import ConnectorName, SourceConnectionTable
from em_radar_api.tables import TeamProfileTable


class InvalidScopeDefinition(ValueError):
    pass


class ScopeDefinitionInUse(ValueError):
    pass


def create_scope_definition(
    session: Session,
    scope: ScopeDefinitionCreate,
) -> ScopeDefinitionRead:
    _validate_scope_definition(session, scope)
    row = ScopeDefinitionTable.model_validate(scope)
    _write(session, row)
    return ScopeDefinitionRead.model_validate(row)


def list_scope_definitions(
    session: Session,
    connection_id: UUID | None = None,
) -> list[ScopeDefinitionRead]:
    statement = select(ScopeDefinitionTable).order_by(ScopeDefinitionTable.created_at)
    if connection_id is not None:
        statement = statement.where(ScopeDefinitionTable.connection_id == connection_id)
    rows = session.exec(statement).all()
    return [ScopeDefinitionRead.model_validate(row) for row in rows]


def get_scope_definition(session: Session, scope_id: UUID) -> ScopeDefinitionRead | None:
    row = session.get(ScopeDefinitionTable, scope_id)
    return ScopeDefinitionRead.model_validate(row) if row is not None else None


def update_scope_definition(
    session: Session,
    scope_id: UUID,
    update: ScopeDefinitionUpdate,
) -> ScopeDefinitionRead | None:
    row = session.get(ScopeDefinitionTable, scope_id)
    if row is None:
        return None

    values = update.model_dump(exclude_unset=True)
    candidate = ScopeDefinitionCreate.model_validate(
        {
            **ScopeDefinitionRead.model_validate(row).model_dump(
                include=set(ScopeDefinitionCreate.model_fields)
            ),
            **values,
        }
    )
    _validate_scope_definition(session, candidate)
    if (
        "connection_id" in values
        and candidate.connection_id != row.connection_id
        and _referencing_teams(session, scope_id)
    ):
        raise ScopeDefinitionInUse("scope definition is referenced by a team")
    row.sqlmodel_update(values)
    row.updated_at = datetime.now(UTC)
    _write(session, row)
    return ScopeDefinitionRead.model_validate(row)


def delete_scope_definition(session: Session, scope_id: UUID) -> bool:
    row = session.get(ScopeDefinitionTable, scope_id)
    if row is None:
        return False
    if _referencing_teams(session, scope_id):
        raise ScopeDefinitionInUse("scope definition is referenced by a team")
    session.delete(row)
    session.commit()
    return True


def _validate_scope_definition(session: Session, scope: ScopeDefinitionCreate) -> None:
    connection = session.get(SourceConnectionTable, scope.connection_id)
    if connection is None:
        raise InvalidScopeDefinition("connection_id must reference an existing connection")
    if connection.connector_name is not ConnectorName.JIRA and scope.scope_type in {
        ScopeType.PROJECT,
        ScopeType.BOARD,
        ScopeType.SAVED_FILTER,
    }:
        raise InvalidScopeDefinition("Jira scope types require a Jira connection")
    _reject_credential_keys(scope.external_ref)
    if len(scope.capabilities) != len(set(scope.capabilities)):
        raise InvalidScopeDefinition("capabilities must not contain duplicates")


def _reject_credential_keys(values: dict[str, object]) -> None:
    for key, value in values.items():
        if is_credential_field_name(key):
            raise InvalidScopeDefinition("external_ref must not contain credentials")
        if isinstance(value, dict):
            _reject_credential_keys(value)


def _referencing_teams(session: Session, scope_id: UUID) -> list[TeamProfileTable]:
    return [
        team for team in session.exec(select(TeamProfileTable)).all() if scope_id in team.scope_ids
    ]


def _write(session: Session, row: ScopeDefinitionTable) -> None:
    session.add(row)
    session.commit()
    session.refresh(row)
