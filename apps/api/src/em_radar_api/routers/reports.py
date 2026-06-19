from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta, timezone
from typing import Literal, Self
from uuid import UUID

from em_radar_connector_demo import DemoConnector
from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.connectors import (
    ConnectorConfigError,
    ConnectorError,
    MergeRequestScope,
    TransitionProvider,
    WorkItemProvider,
    WorkItemScope,
)
from em_radar_core.evaluation import SignalConfig, SignalEvaluator
from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import (
    Confidence,
    EntityType,
    EvaluationContext,
    EvaluationWindow,
    ReportStatus,
    Severity,
    SignalFinding,
    SignalDefinition,
    SignalOrigin,
    Source,
    Sprint,
    SprintState,
    TeamProfile,
    Transition,
    User,
    WindowType,
    WorkItem,
    WorkingMode,
)
from em_radar_core.signals import SignalData, default_registry
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, JsonValue, model_validator
from sqlmodel import Session

from em_radar_api.db import get_session, get_write_session
from em_radar_api.connector_registry import create_connector
from em_radar_api.repositories.canonical import persist_fetch
from em_radar_api.repositories.reports import (
    add_findings,
    create_report,
    get_findings,
    get_report,
    list_reports,
    save_report,
)
from em_radar_api.repositories.signal_configs import list_signal_configs
from em_radar_api.repositories.signal_definitions import list_signal_definitions
from em_radar_api.repositories.scope_definitions import list_scope_definitions
from em_radar_api.repositories.source_connections import (
    get_source_connection,
    instantiate_connector,
)
from em_radar_api.source_connections import ConnectorName
from em_radar_api.tables import (
    EvaluationWindowTable,
    ReportTable,
    SignalFindingTable,
    TeamProfileTable,
)

router = APIRouter()
DEFAULT_KANBAN_REPORT_DAYS = 14


class ReportWindowRequest(BaseModel):
    window_type: WindowType
    sprint_id: UUID | None = None
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.window_type is WindowType.SPRINT:
            if self.sprint_id is None or self.start is not None or self.end is not None:
                raise ValueError("sprint windows require only sprint_id")
        elif self.sprint_id is not None or self.start is None or self.end is None:
            raise ValueError("date-range windows require only start and end")
        return self


class JiraReportRequest(BaseModel):
    connection_id: UUID
    project_external_id: str
    board_external_id: str
    working_mode: WorkingMode
    sprint_length_days: int | None = None

    @model_validator(mode="after")
    def validate_working_mode(self) -> Self:
        if self.working_mode is WorkingMode.KANBAN and self.sprint_length_days is not None:
            raise ValueError("sprint_length_days must be null for kanban reports")
        return self


class ReportRunRequest(BaseModel):
    connector: Literal["demo", "jira"]
    window: ReportWindowRequest | None = None
    jira: JiraReportRequest | None = None

    @model_validator(mode="after")
    def validate_connector_scope(self) -> Self:
        if self.connector == "jira" and self.jira is None:
            raise ValueError("jira reports require jira scope")
        if self.connector == "demo" and self.jira is not None:
            raise ValueError("demo reports do not accept jira scope")
        return self


class FindingResponse(BaseModel):
    signal_id: str
    signal_name: str
    severity: Severity
    confidence: Confidence
    entity_type: EntityType
    entity_id: UUID
    title: str
    reason: str
    recommendation: str | None
    evidence: JsonValue
    source_link: str | None

    @classmethod
    def from_finding(cls, finding: SignalFinding) -> Self:
        return cls.model_validate(finding, from_attributes=True)


class ReportSummaryResponse(BaseModel):
    id: UUID
    evaluation_window_id: UUID
    status: ReportStatus
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    findings_count_by_severity: dict[Severity, int]

    @classmethod
    def from_report(cls, report: ReportTable) -> Self:
        return cls.model_validate(report, from_attributes=True)


class ReportDetailResponse(ReportSummaryResponse):
    signal_pack_snapshot: JsonValue
    findings: list[FindingResponse]

    @classmethod
    def from_report_with_findings(
        cls, report: ReportTable, findings: Sequence[SignalFinding]
    ) -> Self:
        summary = ReportSummaryResponse.from_report(report)
        return cls(
            **summary.model_dump(),
            signal_pack_snapshot=report.signal_pack_snapshot,
            findings=[FindingResponse.from_finding(finding) for finding in findings],
        )


@router.post("/reports/run", response_model=ReportDetailResponse)
async def run_report(
    request: ReportRunRequest,
    session: Session = Depends(get_write_session),
) -> ReportDetailResponse:
    if request.connector == "jira":
        if request.jira is None:
            raise HTTPException(status_code=422, detail="jira reports require jira scope")
        return await _run_jira_report(request.jira, session)
    return await _run_demo_report(request.window, session)


async def _run_demo_report(
    requested_window: ReportWindowRequest | None,
    session: Session,
) -> ReportDetailResponse:
    started_at = datetime.now(timezone.utc)
    connector = DemoConnector({})

    try:
        users = await connector.list_users()
        projects = await connector.list_projects()
        boards = [
            board
            for project in projects
            for board in await connector.list_boards(project.external_id)
        ]
        sprints = [
            sprint for board in boards for sprint in await connector.list_sprints(board.external_id)
        ]
        repositories = await connector.list_repositories()

        team = TeamProfile(
            name="Demo team",
            project_ids=[project.id for project in projects],
            board_ids=[board.id for board in boards],
            repository_ids=[repository.id for repository in repositories],
            created_at=started_at,
            updated_at=started_at,
        )
        window = _evaluation_window(requested_window, sprints, team.id)

        workitems = await _collect(
            connector.fetch_workitems(
                WorkItemScope(
                    project_external_ids=[project.external_id for project in projects],
                    board_external_ids=[board.external_id for board in boards],
                ),
                window,
            )
        )
        merge_requests = await _collect(
            connector.fetch_mergerequests(
                MergeRequestScope(
                    repository_external_ids=[repository.external_id for repository in repositories],
                    include_closed_unmerged=True,
                ),
                window,
            )
        )
        reviews = await _collect(
            connector.fetch_reviews([merge_request.external_id for merge_request in merge_requests])
        )
        transitions = await _collect(
            connector.fetch_transitions(
                "workitem", [workitem.external_id for workitem in workitems]
            )
        )
        comments = [
            *await _collect(
                connector.fetch_comments(
                    "workitem", [workitem.external_id for workitem in workitems]
                )
            ),
            *await _collect(
                connector.fetch_comments(
                    "mergerequest",
                    [merge_request.external_id for merge_request in merge_requests],
                )
            ),
        ]
    finally:
        await connector.close()

    identity = persist_fetch(
        session,
        users=users,
        projects=projects,
        boards=boards,
        sprints=sprints,
        workitems=workitems,
        repositories=repositories,
        mergerequests=merge_requests,
        reviews=reviews,
        transitions=transitions,
        comments=comments,
    )
    session.add(_team_row(team))
    session.commit()
    persisted_window = _persisted_window(window, identity.identity_map)
    session.add(EvaluationWindowTable(**persisted_window.model_dump()))
    session.commit()
    signal_configs = _signal_configs(session)

    report = create_report(
        session,
        ReportTable(
            evaluation_window_id=window.id,
            signal_pack_snapshot=_signal_pack_snapshot(signal_configs),
            status=ReportStatus.PENDING,
            started_at=started_at,
        ),
    )
    report.status = ReportStatus.RUNNING
    save_report(session, report)

    try:
        findings = SignalEvaluator().evaluate(
            SignalData(
                report_id=report.id,
                projects=tuple(projects),
                boards=tuple(boards),
                sprints=tuple(sprints),
                workitems=tuple(workitems),
                repositories=tuple(repositories),
                mergerequests=tuple(merge_requests),
                reviews=tuple(reviews),
                transitions=tuple(transitions),
                comments=tuple(comments),
            ),
            EvaluationContext(now=started_at, window=window, team=team),
            signal_configs,
        )
        persisted_findings = [
            _persisted_finding(finding, identity.identity_map) for finding in findings
        ]
        add_findings(session, persisted_findings)
        report.status = ReportStatus.SUCCEEDED
        report.finished_at = datetime.now(timezone.utc)
        report.findings_count_by_severity = _counts_by_severity(findings)
        save_report(session, report)
    except Exception as error:
        session.rollback()
        report.status = ReportStatus.FAILED
        report.finished_at = datetime.now(timezone.utc)
        report.error = str(error)
        save_report(session, report)
        raise

    return ReportDetailResponse.from_report_with_findings(report, persisted_findings)


async def _run_jira_report(
    request: JiraReportRequest,
    session: Session,
) -> ReportDetailResponse:
    started_at = datetime.now(timezone.utc)
    connection = get_source_connection(session, request.connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="connection not found")
    if connection.connector_name != ConnectorName.JIRA:
        raise HTTPException(status_code=400, detail="connection is not a Jira connection")

    try:
        connector = instantiate_connector(
            session,
            request.connection_id,
            lambda config: create_connector("jira", config),
        )
    except ConnectorConfigError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if connector is None:
        raise HTTPException(status_code=404, detail="connection not found")
    if not isinstance(connector, WorkItemProvider):
        raise HTTPException(status_code=400, detail="connection does not support Jira reports")

    try:
        projects = [
            project
            for project in await connector.list_projects()
            if project.external_id == request.project_external_id
        ]
        if not projects:
            raise HTTPException(status_code=404, detail="Jira project not found")
        boards = [
            board
            for board in await connector.list_boards(request.project_external_id)
            if board.external_id == request.board_external_id
        ]
        if not boards:
            raise HTTPException(status_code=404, detail="Jira board not found")
        sprints = await connector.list_sprints(request.board_external_id)

        team = TeamProfile(
            name=f"{projects[0].key} Jira {request.working_mode.value}",
            connection_ids=[request.connection_id],
            project_ids=[projects[0].id],
            board_ids=[boards[0].id],
            repository_ids=[],
            working_mode=request.working_mode,
            sprint_length_days=request.sprint_length_days,
            created_at=started_at,
            updated_at=started_at,
        )
        window = _jira_evaluation_window(request, sprints, team.id, started_at)
        workitems = await _collect(
            connector.fetch_workitems(
                WorkItemScope(
                    project_external_ids=[request.project_external_id],
                    board_external_ids=[request.board_external_id],
                ),
                window,
            )
        )
        transitions = (
            await _collect(
                connector.fetch_transitions(
                    "workitem",
                    [workitem.external_id for workitem in workitems],
                )
            )
            if isinstance(connector, TransitionProvider)
            else []
        )
    except ConnectorError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        await connector.close()

    identity = persist_fetch(
        session,
        users=_placeholder_jira_users(workitems, transitions),
        projects=projects,
        boards=boards,
        sprints=sprints,
        workitems=workitems,
        transitions=transitions,
    )
    session.add(_team_row(team))
    session.commit()
    persisted_window = _persisted_window(window, identity.identity_map)
    session.add(EvaluationWindowTable(**persisted_window.model_dump()))
    session.commit()
    signal_configs = _signal_configs(session)
    signal_definitions = _signal_definitions(session)
    scope_descriptors = _scope_descriptors(session, request.connection_id)

    report = create_report(
        session,
        ReportTable(
            evaluation_window_id=window.id,
            signal_pack_snapshot=_signal_pack_snapshot(signal_configs, signal_definitions),
            status=ReportStatus.PENDING,
            started_at=started_at,
        ),
    )
    report.status = ReportStatus.RUNNING
    save_report(session, report)

    try:
        data = SignalData(
            report_id=report.id,
            projects=tuple(projects),
            boards=tuple(boards),
            sprints=tuple(sprints),
            workitems=tuple(workitems),
            transitions=tuple(transitions),
        )
        ctx = EvaluationContext(now=started_at, window=window, team=team)
        findings = [
            *SignalEvaluator().evaluate(data, ctx, signal_configs),
            *[
                finding
                for definition in signal_definitions
                for finding in evaluate_signal_definition(
                    definition,
                    data,
                    ctx,
                    JiraConnector.describe_signal_schema(),
                    scope_descriptors,
                )
            ],
        ]
        persisted_findings = [
            _persisted_finding(finding, identity.identity_map) for finding in findings
        ]
        add_findings(session, persisted_findings)
        report.status = ReportStatus.SUCCEEDED
        report.finished_at = datetime.now(timezone.utc)
        report.findings_count_by_severity = _counts_by_severity(findings)
        save_report(session, report)
    except Exception as error:
        session.rollback()
        report.status = ReportStatus.FAILED
        report.finished_at = datetime.now(timezone.utc)
        report.error = str(error)
        save_report(session, report)
        raise

    return ReportDetailResponse.from_report_with_findings(report, persisted_findings)


@router.get("/reports", response_model=list[ReportSummaryResponse])
async def list_reports_endpoint(
    session: Session = Depends(get_session),
) -> list[ReportSummaryResponse]:
    return [ReportSummaryResponse.from_report(report) for report in list_reports(session)]


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
async def get_report_endpoint(
    report_id: UUID,
    session: Session = Depends(get_session),
) -> ReportDetailResponse:
    report = get_report(session, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return ReportDetailResponse.from_report_with_findings(report, get_findings(session, report_id))


def _evaluation_window(
    requested: ReportWindowRequest | None,
    sprints: list[Sprint],
    team_id: UUID,
) -> EvaluationWindow:
    if requested is not None:
        return EvaluationWindow(team_profile_id=team_id, **requested.model_dump())

    active_sprint = next(sprint for sprint in sprints if sprint.state is SprintState.ACTIVE)
    return EvaluationWindow(
        window_type=WindowType.SPRINT,
        sprint_id=active_sprint.id,
        team_profile_id=team_id,
    )


def _jira_evaluation_window(
    request: JiraReportRequest,
    sprints: list[Sprint],
    team_id: UUID,
    now: datetime,
) -> EvaluationWindow:
    if request.working_mode is WorkingMode.KANBAN:
        return EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=now - timedelta(days=DEFAULT_KANBAN_REPORT_DAYS),
            end=now,
            team_profile_id=team_id,
        )

    active_sprint = next(
        (sprint for sprint in sprints if sprint.state is SprintState.ACTIVE),
        None,
    )
    if active_sprint is None:
        raise HTTPException(status_code=422, detail="Jira board has no active sprint")
    return EvaluationWindow(
        window_type=WindowType.SPRINT,
        sprint_id=active_sprint.id,
        team_profile_id=team_id,
    )


def _team_row(team: TeamProfile) -> TeamProfileTable:
    return TeamProfileTable.model_validate(team)


def _persisted_window(window: EvaluationWindow, identity_map: dict[UUID, UUID]) -> EvaluationWindow:
    """Same window with its sprint reference resolved to the persisted internal id (the
    in-memory window keeps the connector sprint id so it lines up with in-memory work items)."""
    if window.sprint_id is None:
        return window
    return window.model_copy(
        update={"sprint_id": identity_map.get(window.sprint_id, window.sprint_id)}
    )


def _persisted_finding(
    finding: SignalFinding, identity_map: dict[UUID, UUID]
) -> SignalFindingTable:
    data = finding.model_dump()
    data["entity_id"] = identity_map.get(finding.entity_id, finding.entity_id)
    return SignalFindingTable(**data)


def _signal_pack_snapshot(
    configs: Sequence[SignalConfig],
    definitions: Sequence[SignalDefinition] | None = None,
) -> dict[str, object]:
    configs_by_id = {config.signal_id: config for config in configs}
    return {
        "schema_id": "emradar.dev/v1",
        "signals": [
            {
                "id": signal.id,
                "name": signal.name,
                "default_severity": signal.default_severity.value,
                "enabled": config.enabled,
                "severity": (config.severity or signal.default_severity).value,
                "params": dict(config.params),
            }
            for signal in (default_registry.get(signal_id) for signal_id in default_registry.ids())
            for config in [configs_by_id[signal.id]]
        ],
        "signal_definitions": [
            {
                "id": str(definition.id),
                "name": definition.name,
                "entity_type": definition.entity_type,
                "target_scopes": [
                    target.model_dump(mode="json") for target in definition.target_scopes
                ],
                "enabled": definition.enabled,
                "origin": definition.origin.value,
                "template_key": definition.template_key,
                "version": definition.version,
            }
            for definition in (definitions or [])
        ],
    }


def _signal_configs(session: Session) -> list[SignalConfig]:
    stored = {config.signal_id: config for config in list_signal_configs(session)}
    configs: list[SignalConfig] = []
    for signal_id in default_registry.ids():
        stored_config = stored.get(signal_id)
        if stored_config is None:
            configs.append(SignalConfig(signal_id=signal_id))
        else:
            configs.append(
                SignalConfig(
                    signal_id=signal_id,
                    enabled=stored_config.enabled,
                    params=stored_config.params,
                    severity=stored_config.severity_override,
                )
            )
    return configs


def _signal_definitions(session: Session) -> list[SignalDefinition]:
    definitions: list[SignalDefinition] = []
    for row in list_signal_definitions(session):
        definitions.append(
            SignalDefinition(
                id=row.id,
                name=row.name,
                description=row.description,
                entity_type=row.entity_type,
                target_scopes=row.target_scopes,
                expression=row.expression,
                report_settings=row.report_settings,
                enabled=row.enabled,
                origin=SignalOrigin(row.origin),
                template_key=row.template_key,
                version=row.version,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return definitions


def _scope_descriptors(session: Session, connection_id: UUID) -> list[ScopeDescriptor]:
    return [
        ScopeDescriptor(
            connector_id=str(scope.connection_id),
            scope_id=str(scope.id),
            scope_type=scope.scope_type.value,
            name=scope.name,
            external_ref=dict(scope.external_ref),
            capabilities=tuple(scope.capabilities),
        )
        for scope in list_scope_definitions(session, connection_id)
    ]


def _placeholder_jira_users(
    workitems: Sequence[WorkItem],
    transitions: Sequence[Transition],
) -> list[User]:
    user_ids = {
        user_id
        for user_id in (
            *[workitem.assignee_id for workitem in workitems],
            *[workitem.reporter_id for workitem in workitems],
            *[transition.actor_id for transition in transitions],
        )
        if user_id is not None
    }
    return [
        User(
            id=user_id,
            source=Source.JIRA,
            external_id=str(user_id),
            display_name="Unknown Jira user",
        )
        for user_id in sorted(user_ids)
    ]


def _counts_by_severity(findings: Sequence[SignalFinding]) -> dict[Severity, int]:
    counts = {severity: 0 for severity in Severity}
    for finding in findings:
        counts[finding.severity] += 1
    return counts


async def _collect[T](iterator: AsyncIterator[T]) -> list[T]:
    return [item async for item in iterator]
