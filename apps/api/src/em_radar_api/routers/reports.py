from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Literal, Self
from uuid import UUID, uuid4

from em_radar_connector_demo import DemoConnector
from em_radar_core.connectors import MergeRequestScope, WorkItemScope
from em_radar_core.evaluation import SignalEvaluator
from em_radar_core.models import (
    Confidence,
    EntityType,
    EvaluationContext,
    EvaluationWindow,
    Severity,
    SignalFinding,
    Sprint,
    SprintState,
    TeamProfile,
    WindowType,
)
from em_radar_core.signals import SignalData
from fastapi import APIRouter
from pydantic import BaseModel, JsonValue, model_validator

router = APIRouter()


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


class ReportRunRequest(BaseModel):
    connector: Literal["demo"]
    window: ReportWindowRequest | None = None


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


class ReportRunResponse(BaseModel):
    findings: list[FindingResponse]


@router.post("/reports/run", response_model=ReportRunResponse)
async def run_report(request: ReportRunRequest) -> ReportRunResponse:
    started_at = datetime.now(timezone.utc)
    connector = DemoConnector({})

    try:
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
        window = _evaluation_window(request.window, sprints, team.id)

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

    findings = SignalEvaluator().evaluate(
        SignalData(
            report_id=uuid4(),
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
    )
    return ReportRunResponse(
        findings=[FindingResponse.from_finding(finding) for finding in findings]
    )


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


async def _collect[T](iterator: AsyncIterator[T]) -> list[T]:
    return [item async for item in iterator]
