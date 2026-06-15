from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session
from starlette.responses import Response

from em_radar_api.connector_registry import create_connector
from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.source_connections import (
    SourceConnectionInUse,
    create_source_connection,
    delete_source_connection,
    get_source_connection,
    instantiate_connector,
    list_source_connections,
    update_source_connection,
)
from em_radar_api.source_connections import (
    SourceConnectionCreate,
    SourceConnectionRead,
    SourceConnectionUpdate,
)
from em_radar_core.connectors import ConnectorBase, ConnectorConfigError, ConnectorError

router = APIRouter()


class ConnectionTestResponse(BaseModel):
    ok: bool
    detail: str
    user_display_name: str | None
    permissions: list[str]


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
    return create_source_connection(session, connection)


@router.patch("/connections/{connection_id}", response_model=SourceConnectionRead)
def patch_connection(
    connection_id: UUID,
    update: SourceConnectionUpdate,
    session: Session = Depends(get_write_session),
) -> SourceConnectionRead:
    try:
        connection = update_source_connection(session, connection_id, update)
    except SourceConnectionInUse as error:
        raise _connection_conflict(error) from error
    if connection is None:
        raise _connection_not_found()
    return connection


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: UUID,
    session: Session = Depends(get_write_session),
) -> Response:
    try:
        if not delete_source_connection(session, connection_id):
            raise _connection_not_found()
    except SourceConnectionInUse as error:
        raise _connection_conflict(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/connections/test", response_model=ConnectionTestResponse)
async def test_connection_draft(connection: SourceConnectionCreate) -> ConnectionTestResponse:
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
        return _failed_test(str(error))
    if connector is None:
        raise _connection_not_found()
    return await _test_connector_instance(connector)


async def _test_connector(
    connector_name: str,
    config: dict[str, object],
) -> ConnectionTestResponse:
    try:
        connector = create_connector(connector_name, config)
    except ConnectorConfigError as error:
        return ConnectionTestResponse(
            ok=False, detail=str(error), user_display_name=None, permissions=[]
        )

    return await _test_connector_instance(connector)


async def _test_connector_instance(connector: ConnectorBase) -> ConnectionTestResponse:
    try:
        return ConnectionTestResponse.model_validate(asdict(await connector.test_connection()))
    except ConnectorError as error:
        return _failed_test(str(error))
    finally:
        await connector.close()


def _failed_test(detail: str) -> ConnectionTestResponse:
    return ConnectionTestResponse(
        ok=False,
        detail=detail,
        user_display_name=None,
        permissions=[],
    )


def _connection_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")


def _connection_conflict(error: SourceConnectionInUse) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
