from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Self
from uuid import UUID

from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.connectors import (
    ConnectorConfigError,
    ConnectorError,
    MergeRequestProvider,
    MergeRequestScope,
    ReviewProvider,
    TransitionProvider,
    WorkItemProvider,
    WorkItemScope,
)
from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.models import (
    Board,
    Confidence,
    EntityType,
    EvaluationContext,
    EvaluationWindow,
    MergeRequest,
    Project,
    ReportStatus,
    Repository,
    Review,
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
from em_radar_core.signals import SignalData
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, JsonValue, model_validator
from sqlmodel import Session, select

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
from em_radar_api.repositories.source_connections import (
    get_source_connection,
    instantiate_connector,
)
from em_radar_api.scope_definitions import ScopeDefinitionTable, ScopeType
from em_radar_api.signal_config_groups import SignalConfigGroupTable
from em_radar_api.signal_definitions import SignalDefinitionTable
from em_radar_api.source_connections import ConnectorName
from em_radar_api.tables import (
    EvaluationWindowTable,
    ReportTable,
    SignalFindingTable,
    TeamProfileTable,
)

router = APIRouter()
DEFAULT_KANBAN_REPORT_DAYS = 14

# Entity types whose signals require a code (VCS) source.  Everything else is treated as
# a board (task-tracker) signal.
_CODE_ENTITY_TYPES: frozenset[str] = frozenset({"mergerequest", "repository"})


class ReportRunRequest(BaseModel):
    connector: Literal["jira"]
    team_profile_id: UUID | None = None

    @model_validator(mode="after")
    def validate_connector_scope(self) -> Self:
        if self.connector == "jira" and self.team_profile_id is None:
            raise ValueError("jira reports require a team_profile_id")
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
    assert request.team_profile_id is not None  # enforced by model validator
    return await _run_team_report(request.team_profile_id, session)


@dataclass
class _BoardFetchResult:
    project: Project
    board: Board
    sprints: list[Sprint]
    workitems: list[WorkItem]
    transitions: list[Transition]
    window: EvaluationWindow


@dataclass
class _CodeFetchResult:
    repositories: list[Repository]
    mergerequests: list[MergeRequest]
    reviews: list[Review]


async def _run_team_report(
    team_profile_id: UUID,
    session: Session,
) -> ReportDetailResponse:
    started_at = datetime.now(timezone.utc)
    team_row = session.get(TeamProfileTable, team_profile_id)
    if team_row is None:
        raise HTTPException(status_code=404, detail="team not found")

    board_scope = _team_board_scope(session, team_row)
    has_code_source = team_row.code_connection_id is not None

    # Require at least one source before running any evaluation.
    if board_scope is None and not has_code_source:
        raise HTTPException(
            status_code=422,
            detail="team has no source attached; attach a task board or a code source",
        )

    team = TeamProfile.model_validate(team_row, from_attributes=True)
    all_definitions = _signal_definitions_for_team(session, team_row)
    board_definitions, code_definitions = _partition_definitions_by_source(all_definitions)

    # Fetch board data (project, board, sprints, workitems, transitions) when board scope present.
    board_data: _BoardFetchResult | None = None
    if board_scope is not None:
        board_data = await _fetch_board_data(session, team, board_scope, started_at)

    # Derive evaluation window from the board, or fall back to a 14-day date range for
    # code-only teams.  Full working-mode window derivation for all source combinations
    # is M6-02 and is out of scope here.
    if board_data is not None:
        window = board_data.window
    else:
        window = EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=started_at - timedelta(days=DEFAULT_KANBAN_REPORT_DAYS),
            end=started_at,
            team_profile_id=team.id,
        )

    # Fetch code data (repositories, merge requests, reviews) when code source is present.
    code_data: _CodeFetchResult | None = None
    if has_code_source and team_row.code_connection_id is not None:
        code_data = await _fetch_code_data(session, team_row.code_connection_id, window)

    board_workitems = board_data.workitems if board_data else []
    board_transitions = board_data.transitions if board_data else []
    code_mergerequests = code_data.mergerequests if code_data else []
    code_reviews = code_data.reviews if code_data else []

    identity = persist_fetch(
        session,
        users=(
            _placeholder_jira_users(board_workitems, board_transitions)
            + _placeholder_code_users(code_mergerequests, code_reviews)
        ),
        projects=[board_data.project] if board_data else [],
        boards=[board_data.board] if board_data else [],
        sprints=board_data.sprints if board_data else [],
        workitems=board_workitems,
        transitions=board_transitions,
        repositories=code_data.repositories if code_data else [],
        mergerequests=code_mergerequests,
        reviews=code_reviews,
    )
    persisted_window = _persisted_window(window, identity.identity_map)
    session.add(EvaluationWindowTable(**persisted_window.model_dump()))
    session.commit()

    skipped_signals = _skipped_signal_entries(
        board_definitions=board_definitions,
        code_definitions=code_definitions,
        board_attached=board_scope is not None,
        code_attached=has_code_source,
    )

    report = create_report(
        session,
        ReportTable(
            evaluation_window_id=window.id,
            signal_pack_snapshot=_team_signal_pack_snapshot(
                team_row, all_definitions, skipped_signals
            ),
            status=ReportStatus.PENDING,
            started_at=started_at,
        ),
    )
    report.status = ReportStatus.RUNNING
    save_report(session, report)

    try:
        signal_data = SignalData(
            report_id=report.id,
            projects=(board_data.project,) if board_data else (),
            boards=(board_data.board,) if board_data else (),
            sprints=tuple(board_data.sprints) if board_data else (),
            workitems=tuple(board_workitems),
            transitions=tuple(board_transitions),
            repositories=tuple(code_data.repositories) if code_data else (),
            mergerequests=tuple(code_mergerequests),
            reviews=tuple(code_reviews),
        )
        ctx = EvaluationContext(now=started_at, window=window, team=team)

        # Evaluate board signals (workitem/sprint/issue entity types) when board source attached.
        findings: list[SignalFinding] = []
        if board_data is not None and board_scope is not None:
            scope_descriptor = _scope_descriptor(board_scope)
            for definition in board_definitions:
                findings.extend(
                    evaluate_signal_definition(
                        definition,
                        signal_data,
                        ctx,
                        JiraConnector.describe_signal_schema(),
                        [scope_descriptor],
                    )
                )

        # Code signals (mergerequest entity type) are evaluated when code source is attached.
        # Full MR signal evaluation ships in M4; currently produces no findings.

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


async def _fetch_board_data(
    session: Session,
    team: TeamProfile,
    board_scope: ScopeDefinitionTable,
    started_at: datetime,
) -> _BoardFetchResult:
    """Fetch Jira board data (project, board, sprints, workitems, transitions) and derive window."""
    connection = get_source_connection(session, board_scope.connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="connection not found")
    if connection.connector_name != ConnectorName.JIRA:
        raise HTTPException(status_code=400, detail="team board scope is not a Jira connection")

    try:
        connector = instantiate_connector(
            session,
            board_scope.connection_id,
            lambda config: create_connector("jira", config),
        )
    except ConnectorConfigError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if connector is None:
        raise HTTPException(status_code=404, detail="connection not found")
    if not isinstance(connector, WorkItemProvider):
        raise HTTPException(status_code=400, detail="connection does not support Jira reports")

    board_external_id = str(board_scope.external_ref.get("id"))
    try:
        project, board = await _find_jira_board(connector, board_external_id)
        if project is None or board is None:
            raise HTTPException(status_code=404, detail="Jira board not found")
        sprints = await connector.list_sprints(board_external_id)
        window = _jira_evaluation_window(team, sprints, team.id, started_at)
        workitems = await _collect(
            connector.fetch_workitems(
                WorkItemScope(
                    project_external_ids=[project.external_id],
                    board_external_ids=[board_external_id],
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

    return _BoardFetchResult(
        project=project,
        board=board,
        sprints=sprints,
        workitems=workitems,
        transitions=transitions,
        window=window,
    )


async def _fetch_code_data(
    session: Session,
    code_connection_id: UUID,
    window: EvaluationWindow,
) -> _CodeFetchResult:
    """Fetch repositories, merge requests, and (if available) reviews from the code connection."""
    code_connection = get_source_connection(session, code_connection_id)
    if code_connection is None:
        raise HTTPException(status_code=404, detail="code connection not found")

    try:
        code_connector = instantiate_connector(
            session,
            code_connection_id,
            lambda config: create_connector(str(code_connection.connector_name), config),
        )
    except ConnectorConfigError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if code_connector is None:
        raise HTTPException(status_code=404, detail="code connection not found")

    if not isinstance(code_connector, MergeRequestProvider):
        # Connector registered but does not provide MR data; code signals produce no findings.
        await code_connector.close()
        return _CodeFetchResult(repositories=[], mergerequests=[], reviews=[])

    try:
        repositories = await code_connector.list_repositories()
        mr_scope = MergeRequestScope(
            repository_external_ids=[repo.external_id for repo in repositories]
        )
        mergerequests = await _collect(code_connector.fetch_mergerequests(mr_scope, window))
        reviews = (
            await _collect(code_connector.fetch_reviews([mr.external_id for mr in mergerequests]))
            if isinstance(code_connector, ReviewProvider)
            else []
        )
    except ConnectorError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        await code_connector.close()

    return _CodeFetchResult(repositories=repositories, mergerequests=mergerequests, reviews=reviews)


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


def _jira_evaluation_window(
    team: TeamProfile,
    sprints: list[Sprint],
    team_id: UUID,
    now: datetime,
) -> EvaluationWindow:
    if team.working_mode is WorkingMode.KANBAN:
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


def _partition_definitions_by_source(
    definitions: list[SignalDefinition],
) -> tuple[list[SignalDefinition], list[SignalDefinition]]:
    """Split signal definitions into (board_signals, code_signals) by entity_type."""
    board: list[SignalDefinition] = []
    code: list[SignalDefinition] = []
    for definition in definitions:
        if definition.entity_type in _CODE_ENTITY_TYPES:
            code.append(definition)
        else:
            # Default: treat unknown entity types as board signals so they participate
            # in the board evaluation path rather than being silently dropped.
            board.append(definition)
    return board, code


def _skipped_signal_entries(
    *,
    board_definitions: list[SignalDefinition],
    code_definitions: list[SignalDefinition],
    board_attached: bool,
    code_attached: bool,
) -> list[dict[str, object]]:
    """Build skip-note entries for signal definitions whose required source is absent."""
    entries: list[dict[str, object]] = []
    if not board_attached:
        for defn in board_definitions:
            entries.append(
                {"id": str(defn.id), "name": defn.name, "reason": "board source not attached"}
            )
    if not code_attached:
        for defn in code_definitions:
            entries.append(
                {"id": str(defn.id), "name": defn.name, "reason": "code source not attached"}
            )
    return entries


def _team_signal_pack_snapshot(
    team_row: TeamProfileTable,
    definitions: Sequence[SignalDefinition],
    skipped_signals: Sequence[dict[str, object]] = (),
) -> dict[str, object]:
    return {
        "schema_id": "emradar.dev/v1",
        "signal_config_group_ids": [str(group_id) for group_id in team_row.signal_config_group_ids],
        "signal_definitions": [
            {
                "id": str(definition.id),
                "name": definition.name,
                "entity_type": definition.entity_type,
                "enabled": definition.enabled,
                "origin": definition.origin.value,
                "template_key": definition.template_key,
                "version": definition.version,
            }
            for definition in definitions
        ],
        "skipped_signals": list(skipped_signals),
    }


def _team_board_scope(session: Session, team_row: TeamProfileTable) -> ScopeDefinitionTable | None:
    scopes = session.exec(
        select(ScopeDefinitionTable).where(ScopeDefinitionTable.id.in_(team_row.scope_ids))
    ).all()
    return next((scope for scope in scopes if scope.scope_type is ScopeType.BOARD), None)


async def _find_jira_board(
    connector: WorkItemProvider, board_external_id: str
) -> tuple[Project, Board] | tuple[None, None]:
    for project in await connector.list_projects():
        for board in await connector.list_boards(project.external_id):
            if board.external_id == board_external_id:
                return project, board
    return None, None


def _signal_definitions_for_team(
    session: Session, team_row: TeamProfileTable
) -> list[SignalDefinition]:
    groups = session.exec(
        select(SignalConfigGroupTable).where(
            SignalConfigGroupTable.id.in_(team_row.signal_config_group_ids)
        )
    ).all()
    ordered_ids: list[UUID] = []
    seen: set[UUID] = set()
    for group in groups:
        for signal_id in group.signal_ids:
            if signal_id not in seen:
                seen.add(signal_id)
                ordered_ids.append(signal_id)

    rows = session.exec(
        select(SignalDefinitionTable).where(SignalDefinitionTable.id.in_(ordered_ids))
    ).all()
    rows_by_id = {row.id: row for row in rows}
    return [
        _definition_from_row(rows_by_id[signal_id])
        for signal_id in ordered_ids
        if signal_id in rows_by_id and rows_by_id[signal_id].enabled
    ]


def _definition_from_row(row: SignalDefinitionTable) -> SignalDefinition:
    return SignalDefinition(
        id=row.id,
        name=row.name,
        description=row.description,
        entity_type=row.entity_type,
        expression=row.expression,
        report_settings=row.report_settings,
        enabled=row.enabled,
        origin=SignalOrigin(row.origin),
        template_key=row.template_key,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _scope_descriptor(scope: ScopeDefinitionTable) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id=str(scope.connection_id),
        scope_id=str(scope.id),
        scope_type=scope.scope_type.value,
        name=scope.name,
        external_ref=dict(scope.external_ref),
        capabilities=tuple(scope.capabilities),
    )


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


def _placeholder_code_users(
    mergerequests: Sequence[MergeRequest],
    reviews: Sequence[Review],
) -> list[User]:
    """Placeholder User rows for MR authors and review reviewers.

    MergeRequestTable.author_id is a required FK; users must be persisted before MRs.
    """
    author_sources: dict[UUID, Source] = {}
    for mr in mergerequests:
        author_sources[mr.author_id] = mr.source
    default_source = mergerequests[0].source if mergerequests else Source.GITLAB
    for review in reviews:
        if review.reviewer_id not in author_sources:
            author_sources[review.reviewer_id] = default_source
    return [
        User(
            id=user_id,
            source=source,
            external_id=str(user_id),
            display_name="Unknown code user",
        )
        for user_id, source in sorted(author_sources.items())
    ]


def _counts_by_severity(findings: Sequence[SignalFinding]) -> dict[Severity, int]:
    counts = {severity: 0 for severity in Severity}
    for finding in findings:
        counts[finding.severity] += 1
    return counts


async def _collect[T](iterator: AsyncIterator[T]) -> list[T]:
    return [item async for item in iterator]
