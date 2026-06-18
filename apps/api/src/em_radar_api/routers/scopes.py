from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session
from starlette.responses import Response

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.scope_definitions import (
    InvalidScopeDefinition,
    ScopeDefinitionInUse,
    create_scope_definition,
    delete_scope_definition,
    get_scope_definition,
    list_scope_definitions,
    update_scope_definition,
)
from em_radar_api.scope_definitions import (
    ScopeDefinitionCreate,
    ScopeDefinitionRead,
    ScopeDefinitionUpdate,
)

router = APIRouter()


@router.get("/scopes", response_model=list[ScopeDefinitionRead])
def list_scopes(
    connection_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[ScopeDefinitionRead]:
    return list_scope_definitions(session, connection_id)


@router.post("/scopes", response_model=ScopeDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_scope(
    scope: ScopeDefinitionCreate,
    session: Session = Depends(get_write_session),
) -> ScopeDefinitionRead:
    try:
        return create_scope_definition(session, scope)
    except InvalidScopeDefinition as error:
        raise _invalid_scope(error) from error


@router.get("/scopes/{scope_id}", response_model=ScopeDefinitionRead)
def get_scope(scope_id: UUID, session: Session = Depends(get_session)) -> ScopeDefinitionRead:
    scope = get_scope_definition(session, scope_id)
    if scope is None:
        raise _scope_not_found()
    return scope


@router.patch("/scopes/{scope_id}", response_model=ScopeDefinitionRead)
def patch_scope(
    scope_id: UUID,
    update: ScopeDefinitionUpdate,
    session: Session = Depends(get_write_session),
) -> ScopeDefinitionRead:
    try:
        scope = update_scope_definition(session, scope_id, update)
    except InvalidScopeDefinition as error:
        raise _invalid_scope(error) from error
    if scope is None:
        raise _scope_not_found()
    return scope


@router.delete("/scopes/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scope(scope_id: UUID, session: Session = Depends(get_write_session)) -> Response:
    try:
        if not delete_scope_definition(session, scope_id):
            raise _scope_not_found()
    except ScopeDefinitionInUse as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _scope_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scope not found")


def _invalid_scope(error: InvalidScopeDefinition) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
