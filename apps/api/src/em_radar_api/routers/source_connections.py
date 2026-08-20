# SPDX-License-Identifier: Apache-2.0

from dataclasses import asdict
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session
from starlette.responses import Response

from em_radar_connector_jira.connector import JiraFieldInfo

from em_radar_api.connector_registry import create_connector
from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.source_connections import (
    SourceConnectionDuplicateName,
    SourceConnectionInUse,
    SourceConnectionInvalidName,
    create_source_connection,
    delete_source_connection,
    get_source_connection,
    instantiate_connector,
    list_source_connections,
    update_source_connection,
)
from em_radar_api.source_connections import (
    ConnectorName,
    SourceConnectionCreate,
    SourceConnectionRead,
    SourceConnectionUpdate,
)
from em_radar_core.connectors import (
    ConnectionErrorCode,
    ConnectorAuthError,
    ConnectorBase,
    ConnectorConfigError,
    ConnectorDataError,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorRateLimitedError,
    ConnectorTransientError,
    WorkItemProvider,
)
from em_radar_core.models import Board, BoardType, Project, Sprint, SprintState


@runtime_checkable
class FieldDiscoveryConnector(Protocol):
    async def discover_fields(self) -> list[JiraFieldInfo]: ...
    async def close(self) -> None: ...


router = APIRouter()


class ConnectionTestResponse(BaseModel):
    ok: bool
    detail: str
    user_display_name: str | None
    permissions: list[str]
    code: ConnectionErrorCode | None = None


class SourceConnectionDraft(BaseModel):
    """Request body for the draft connection test — no name required since nothing is persisted."""

    connector_name: ConnectorName
    config: dict[str, object] = {}


class ProjectResponse(BaseModel):
    id: UUID
    external_id: str
    key: str
    name: str

    @classmethod
    def from_project(cls, project: Project) -> "ProjectResponse":
        return cls.model_validate(project, from_attributes=True)


class BoardResponse(BaseModel):
    id: UUID
    external_id: str
    project_id: UUID
    name: str
    type: BoardType | None

    @classmethod
    def from_board(cls, board: Board) -> "BoardResponse":
        return cls.model_validate(board, from_attributes=True)


class SprintResponse(BaseModel):
    id: UUID
    external_id: str
    board_id: UUID
    name: str
    state: SprintState
    start_date: datetime | None
    end_date: datetime | None
    complete_date: datetime | None
    goal: str | None

    @classmethod
    def from_sprint(cls, sprint: Sprint) -> "SprintResponse":
        return cls.model_validate(sprint, from_attributes=True)


@router.get("/connections", response_model=list[SourceConnectionRead])
def list_connections(session: Session = Depends(get_session)) -> list[SourceConnectionRead]:
    return list_source_connections(session)


@router.post(
    "/connections",
    response_model=SourceConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_connection(
    connection: SourceConnectionCreate,
    session: Session = Depends(get_write_session),
) -> SourceConnectionRead:
    try:
        return create_source_connection(session, connection)
    except SourceConnectionDuplicateName as error:
        raise _connection_duplicate_name(error) from error


@router.patch("/connections/{connection_id}", response_model=SourceConnectionRead)
def patch_connection(
    connection_id: UUID,
    update: SourceConnectionUpdate,
    session: Session = Depends(get_write_session),
) -> SourceConnectionRead:
    try:
        connection = update_source_connection(session, connection_id, update)
    except SourceConnectionInvalidName as error:
        raise _connection_invalid_name(error) from error
    except SourceConnectionDuplicateName as error:
        raise _connection_duplicate_name(error) from error
    except SourceConnectionInUse as error:
        raise _connection_conflict(error) from error
    if connection is None:
        raise _connection_not_found()
    return connection


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: UUID,
    force: bool = False,
    session: Session = Depends(get_write_session),
) -> Response:
    """Delete a connection and, when ``force=true``, cascade to its cached data and team refs.

    Without ``force``, returns 409 with the list of dependent teams if any team still
    references this connection — the client can surface this as a warning and re-submit
    with ``force=true`` after the user confirms.  Outbound calls to source systems are
    never made.
    """
    try:
        if not delete_source_connection(session, connection_id, force=force):
            raise _connection_not_found()
    except SourceConnectionInUse as error:
        raise _connection_conflict(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/connections/test", response_model=ConnectionTestResponse)
async def test_connection_draft(connection: SourceConnectionDraft) -> ConnectionTestResponse:
    return await _test_connector(connection.connector_name, connection.config)


@router.post("/connections/{connection_id}/test", response_model=ConnectionTestResponse)
async def test_existing_connection(
    connection_id: UUID,
    session: Session = Depends(get_session),
) -> ConnectionTestResponse:
    connection = get_source_connection(session, connection_id)
    if connection is None:
        raise _connection_not_found()
    try:
        connector = instantiate_connector(
            session,
            connection_id,
            lambda config: create_connector(connection.connector_name, config),
        )
    except ConnectorConfigError as error:
        return _failed_test(str(error), _error_code(error))
    if connector is None:
        raise _connection_not_found()
    return await _test_connector_instance(connector)


@router.get("/connections/{connection_id}/projects", response_model=list[ProjectResponse])
async def list_connection_projects(
    connection_id: UUID,
    session: Session = Depends(get_session),
) -> list[ProjectResponse]:
    connector = _workitem_connector(session, connection_id)
    try:
        return [ProjectResponse.from_project(p) for p in await connector.list_projects()]
    except ConnectorError as error:
        raise HTTPException(status_code=_picker_status(error), detail=str(error)) from error
    finally:
        await connector.close()


@router.get(
    "/connections/{connection_id}/projects/{project_id}/boards",
    response_model=list[BoardResponse],
)
async def list_connection_boards(
    connection_id: UUID,
    project_id: str,
    session: Session = Depends(get_session),
) -> list[BoardResponse]:
    connector = _workitem_connector(session, connection_id)
    try:
        return [BoardResponse.from_board(b) for b in await connector.list_boards(project_id)]
    except ConnectorError as error:
        raise HTTPException(status_code=_picker_status(error), detail=str(error)) from error
    finally:
        await connector.close()


@router.get(
    "/connections/{connection_id}/boards/{board_id}/sprints",
    response_model=list[SprintResponse],
)
async def list_connection_sprints(
    connection_id: UUID,
    board_id: str,
    session: Session = Depends(get_session),
) -> list[SprintResponse]:
    connector = _workitem_connector(session, connection_id)
    try:
        return [SprintResponse.from_sprint(s) for s in await connector.list_sprints(board_id)]
    except ConnectorError as error:
        raise HTTPException(status_code=_picker_status(error), detail=str(error)) from error
    finally:
        await connector.close()


@router.get("/connections/{connection_id}/jira/fields", response_model=list[JiraFieldInfo])
async def list_jira_fields(
    connection_id: UUID,
    session: Session = Depends(get_session),
) -> list[JiraFieldInfo]:
    connector = await _jira_field_connector(session, connection_id)
    try:
        return await connector.discover_fields()
    except ConnectorError as error:
        raise HTTPException(status_code=_picker_status(error), detail=str(error)) from error
    finally:
        await connector.close()


async def _test_connector(
    connector_name: str,
    config: dict[str, object],
) -> ConnectionTestResponse:
    try:
        connector = create_connector(connector_name, config)
    except ConnectorConfigError as error:
        return _failed_test(str(error), _error_code(error))

    return await _test_connector_instance(connector)


async def _test_connector_instance(connector: ConnectorBase) -> ConnectionTestResponse:
    try:
        return ConnectionTestResponse.model_validate(asdict(await connector.test_connection()))
    except ConnectorError as error:
        return _failed_test(str(error), _error_code(error))
    finally:
        await connector.close()


async def _jira_field_connector(session: Session, connection_id: UUID) -> "FieldDiscoveryConnector":
    connection = get_source_connection(session, connection_id)
    if connection is None:
        raise _connection_not_found()
    if connection.connector_name != ConnectorName.JIRA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="connection is not a Jira connection",
        )
    try:
        connector = instantiate_connector(
            session,
            connection_id,
            lambda config: create_connector("jira", config),
        )
    except ConnectorConfigError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    if connector is None:
        raise _connection_not_found()
    if not isinstance(connector, FieldDiscoveryConnector):
        await connector.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="connection does not support Jira field discovery",
        )
    return connector


def _workitem_connector(session: Session, connection_id: UUID) -> WorkItemProvider:
    connection = get_source_connection(session, connection_id)
    if connection is None:
        raise _connection_not_found()
    if connection.connector_name != ConnectorName.JIRA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="connection is not a Jira connection",
        )
    try:
        connector = instantiate_connector(
            session,
            connection_id,
            lambda config: create_connector("jira", config),
        )
    except ConnectorConfigError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    if connector is None:
        raise _connection_not_found()
    if not isinstance(connector, WorkItemProvider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="connection does not support Jira work-item lists",
        )
    return connector


def _failed_test(detail: str, code: ConnectionErrorCode) -> ConnectionTestResponse:
    return ConnectionTestResponse(
        ok=False,
        detail=detail,
        user_display_name=None,
        permissions=[],
        code=code,
    )


def _error_code(error: ConnectorError) -> ConnectionErrorCode:
    if isinstance(error, ConnectorAuthError):
        return "auth"
    if isinstance(error, ConnectorNotFoundError):
        return "not_found"
    if isinstance(error, ConnectorRateLimitedError):
        return "rate_limited"
    if isinstance(error, ConnectorTransientError):
        return "transient"
    if isinstance(error, ConnectorConfigError):
        return "config"
    if isinstance(error, ConnectorDataError):
        return "data"
    return "unknown"


def _picker_status(error: ConnectorError) -> int:
    code = _error_code(error)
    if code == "auth":
        return status.HTTP_401_UNAUTHORIZED
    if code == "not_found":
        return status.HTTP_404_NOT_FOUND
    if code == "rate_limited":
        return status.HTTP_429_TOO_MANY_REQUESTS
    if code == "config":
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    return status.HTTP_502_BAD_GATEWAY


def _connection_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")


def _connection_conflict(error: SourceConnectionInUse) -> HTTPException:
    detail: object = {
        "message": str(error),
        "dependent_teams": [
            {"id": str(team.id), "name": team.name} for team in error.dependent_teams
        ],
    }
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _connection_duplicate_name(error: SourceConnectionDuplicateName) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def _connection_invalid_name(error: SourceConnectionInvalidName) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
