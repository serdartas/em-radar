from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.signal_definitions import (
    DuplicateSignalName,
    InvalidSignalDefinition,
    create_signal_definition,
    delete_signal_definition,
    get_signal_definition,
    list_signal_definitions,
    update_signal_definition,
)
from em_radar_api.signal_definitions import (
    SignalDefinitionCreate,
    SignalDefinitionRead,
    SignalDefinitionUpdate,
)
from em_radar_config import restore_jira_signal_template, seed_jira_signal_templates

router = APIRouter()


class SignalTemplateRead(BaseModel):
    key: str
    name: str
    description: str
    required_connector_type: str
    entity_type: str
    required_scope_capabilities: list[str]
    expression: dict[str, object]
    report_settings: dict[str, object]


@router.get("/signal-templates", response_model=list[SignalTemplateRead])
def list_signal_templates_route() -> list[SignalTemplateRead]:
    return [
        SignalTemplateRead(
            key=template.key,
            name=template.name,
            description=template.description,
            required_connector_type=template.required_connector_type,
            entity_type=template.entity_type,
            required_scope_capabilities=list(template.required_scope_capabilities),
            expression=template.expression,
            report_settings=template.report_settings.model_dump(mode="json"),
        )
        for template in seed_jira_signal_templates()
    ]


@router.post("/signal-templates/{template_key}/restore", response_model=SignalTemplateRead)
def restore_signal_template_route(template_key: str) -> SignalTemplateRead:
    try:
        template = restore_jira_signal_template(template_key)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"signal template not found: {template_key}",
        ) from error
    return SignalTemplateRead(
        key=template.key,
        name=template.name,
        description=template.description,
        required_connector_type=template.required_connector_type,
        entity_type=template.entity_type,
        required_scope_capabilities=list(template.required_scope_capabilities),
        expression=template.expression,
        report_settings=template.report_settings.model_dump(mode="json"),
    )


@router.get("/signal-definitions", response_model=list[SignalDefinitionRead])
def list_signal_definitions_route(
    session: Session = Depends(get_session),
) -> list[SignalDefinitionRead]:
    return list_signal_definitions(session)


@router.post(
    "/signal-definitions",
    response_model=SignalDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_signal_definition_route(
    definition: SignalDefinitionCreate,
    session: Session = Depends(get_write_session),
) -> SignalDefinitionRead:
    try:
        return create_signal_definition(session, definition)
    except DuplicateSignalName as error:
        raise _conflict(error) from error
    except InvalidSignalDefinition as error:
        raise _invalid(error) from error


@router.get("/signal-definitions/{definition_id}", response_model=SignalDefinitionRead)
def get_signal_definition_route(
    definition_id: UUID,
    session: Session = Depends(get_session),
) -> SignalDefinitionRead:
    definition = get_signal_definition(session, definition_id)
    if definition is None:
        raise _not_found(definition_id)
    return definition


@router.patch("/signal-definitions/{definition_id}", response_model=SignalDefinitionRead)
def update_signal_definition_route(
    definition_id: UUID,
    update: SignalDefinitionUpdate,
    session: Session = Depends(get_write_session),
) -> SignalDefinitionRead:
    try:
        definition = update_signal_definition(session, definition_id, update)
    except DuplicateSignalName as error:
        raise _conflict(error) from error
    except InvalidSignalDefinition as error:
        raise _invalid(error) from error
    if definition is None:
        raise _not_found(definition_id)
    return definition


@router.delete("/signal-definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_signal_definition_route(
    definition_id: UUID,
    session: Session = Depends(get_write_session),
) -> None:
    if not delete_signal_definition(session, definition_id):
        raise _not_found(definition_id)


def _not_found(definition_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"signal definition not found: {definition_id}",
    )


def _invalid(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))


def _conflict(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
