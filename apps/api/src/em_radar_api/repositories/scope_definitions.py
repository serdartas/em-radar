from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session, select

from em_radar_api.repositories.source_connections import CREDENTIAL_FIELD_NAMES
from em_radar_api.scope_definitions import (
    ScopeDefinitionCreate,
    ScopeDefinitionRead,
    ScopeDefinitionTable,
    ScopeDefinitionUpdate,
    ScopeType,
)
from em_radar_api.source_connections import ConnectorName, SourceConnectionTable
from em_radar_api.tables import TeamProfileTable
from em_radar_core.models import Board, BoardType, Project


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


def upsert_jira_project_scope(
    session: Session,
    connection_id: UUID,
    project: Project,
) -> ScopeDefinitionRead:
    return _upsert_connector_scope(
        session,
        ScopeDefinitionCreate(
            connection_id=connection_id,
            name=project.name,
            scope_type=ScopeType.PROJECT,
            external_ref={
                "type": "jira_project",
                "id": project.external_id,
                "key": project.key,
                "name": project.name,
            },
            capabilities=["statuses", "labels"],
        ),
    )


def upsert_jira_board_scope(
    session: Session,
    connection_id: UUID,
    board: Board,
) -> ScopeDefinitionRead:
    capabilities = ["statuses", "labels"]
    if board.type is BoardType.SCRUM:
        capabilities.insert(0, "sprint")
    elif board.type is BoardType.KANBAN:
        capabilities.insert(0, "kanban")
    return _upsert_connector_scope(
        session,
        ScopeDefinitionCreate(
            connection_id=connection_id,
            name=board.name,
            scope_type=ScopeType.BOARD,
            external_ref={
                "type": "jira_board",
                "id": board.external_id,
                "key": None,
                "name": board.name,
            },
            capabilities=capabilities,
        ),
    )


def _upsert_connector_scope(
    session: Session,
    scope: ScopeDefinitionCreate,
) -> ScopeDefinitionRead:
    row = session.exec(
        select(ScopeDefinitionTable).where(
            ScopeDefinitionTable.connection_id == scope.connection_id,
            ScopeDefinitionTable.scope_type == scope.scope_type,
        )
    ).all()
    matching_row = next(
        (
            item
            for item in row
            if item.external_ref.get("type") == scope.external_ref.get("type")
            and item.external_ref.get("id") == scope.external_ref.get("id")
        ),
        None,
    )
    if matching_row is None:
        return create_scope_definition(session, scope)
    matching_row.sqlmodel_update(scope.model_dump())
    matching_row.updated_at = datetime.now(UTC)
    _write(session, matching_row)
    return ScopeDefinitionRead.model_validate(matching_row)


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
        if key.lower() in CREDENTIAL_FIELD_NAMES:
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
