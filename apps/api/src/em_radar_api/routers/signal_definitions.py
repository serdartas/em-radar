from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select

from em_radar_api.db import get_session, get_write_session
from em_radar_api.repositories.signal_definitions import (
    DuplicateSignalName,
    create_signal_definition,
    delete_signal_definition,
    get_signal_definition,
    list_signal_definitions,
    update_signal_definition,
)
from em_radar_api.scope_definitions import ScopeDefinitionTable
from em_radar_api.signal_definitions import (
    SignalDefinitionCreate,
    SignalDefinitionRead,
    SignalDefinitionUpdate,
)
from em_radar_api.tables import (
    BoardTable,
    ProjectTable,
    SprintTable,
    TransitionTable,
    WorkItemTable,
)
from em_radar_config import restore_jira_signal_template, seed_jira_signal_templates
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.evaluation import ScopeDescriptor, preview_signal_definition
from em_radar_core.models import (
    EvaluationContext,
    EvaluationWindow,
    ReportSettings,
    SignalDefinition,
    SignalOrigin,
    TeamProfile,
    WindowType,
)
from em_radar_core.signals import SignalData

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


class SignalDefinitionPreview(BaseModel):
    match_count: int
    samples: list[dict[str, object]]
    warnings: list[str]


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


@router.post("/signal-definitions/preview", response_model=SignalDefinitionPreview)
def preview_signal_definition_route(
    definition: SignalDefinitionCreate,
    scope_ids: list[UUID] = Query(default=[]),
    session: Session = Depends(get_session),
) -> SignalDefinitionPreview:
    model = SignalDefinition(
        id=uuid4(),
        name=definition.name,
        description=definition.description,
        entity_type=definition.entity_type,
        expression=definition.expression,
        report_settings=ReportSettings.model_validate(definition.report_settings),
        enabled=definition.enabled,
        origin=SignalOrigin(definition.origin),
        template_key=definition.template_key,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    scopes = _scope_descriptors_by_ids(session, scope_ids)
    now = datetime.now(UTC)
    preview = preview_signal_definition(
        model,
        SignalData(
            report_id=uuid4(),
            projects=tuple(session.exec(select(ProjectTable)).all()),
            boards=tuple(session.exec(select(BoardTable)).all()),
            sprints=tuple(session.exec(select(SprintTable)).all()),
            workitems=tuple(session.exec(select(WorkItemTable)).all()),
            transitions=tuple(session.exec(select(TransitionTable)).all()),
        ),
        EvaluationContext(
            now=now,
            window=EvaluationWindow(
                window_type=WindowType.DATE_RANGE,
                start=now,
                end=now,
                team_profile_id=uuid4(),
            ),
            team=TeamProfile(name="Preview", created_at=now, updated_at=now),
        ),
        JiraConnector.describe_signal_schema(),
        scopes,
    )
    return SignalDefinitionPreview.model_validate(preview)


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


def _scope_descriptors_by_ids(session: Session, scope_ids: list[UUID]) -> list[ScopeDescriptor]:
    if not scope_ids:
        return []
    rows = session.exec(
        select(ScopeDefinitionTable).where(ScopeDefinitionTable.id.in_(scope_ids))
    ).all()
    return [
        ScopeDescriptor(
            connector_id=str(scope.connection_id),
            scope_id=str(scope.id),
            scope_type=scope.scope_type.value,
            name=scope.name,
            external_ref=dict(scope.external_ref),
            capabilities=tuple(scope.capabilities),
        )
        for scope in rows
    ]


def _not_found(definition_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"signal definition not found: {definition_id}",
    )


def _conflict(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
