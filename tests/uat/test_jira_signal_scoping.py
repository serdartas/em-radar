from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from em_radar_connector_jira.connector import JiraConnector
from em_radar_core.evaluation import (
    ScopeDescriptor,
    evaluate_signal_definition,
    preview_signal_definition,
)
from em_radar_core.models import (
    Board,
    BoardType,
    Project,
    ReportSettings,
    SignalDefinition,
    SignalOrigin,
    SignalTargetScope,
    Source,
    Sprint,
    SprintState,
    StatusCategory,
    TeamProfile,
    EvaluationContext,
    EvaluationWindow,
    WindowType,
    WorkItem,
    WorkItemType,
)
from em_radar_core.signals import SignalData


NOW = datetime(2026, 1, 20, 12, tzinfo=timezone.utc)
PROJECT_ID = uuid4()
KANBAN_PROJECT_ID = uuid4()
SCRUM_BOARD_ID = uuid4()
KANBAN_BOARD_ID = uuid4()
SUPPORT_PROJECT_ID = uuid4()
SPRINT_ID = uuid4()


def test_scoped_jira_rules_do_not_leak_to_sibling_scopes() -> None:
    scrum = _signal(
        "Stale Scrum work",
        "scrum-scope",
        "board",
        "age_in_current_status",
        {"amount": 3, "unit": "days"},
    )
    kanban = _signal(
        "Kanban aging",
        "kanban-scope",
        "board",
        "age_since_created",
        {"amount": 10, "unit": "days"},
    )
    support = _signal(
        "Support open longer than 3 days",
        "support-scope",
        "project",
        "age_since_created",
        {"amount": 3, "unit": "days"},
    )
    data = _data()
    scopes = _scopes()

    scrum_findings = evaluate_signal_definition(
        scrum,
        data,
        _context(),
        JiraConnector.describe_signal_schema(),
        scopes,
    )
    kanban_findings = evaluate_signal_definition(
        kanban,
        data,
        _context(),
        JiraConnector.describe_signal_schema(),
        scopes,
    )
    support_findings = evaluate_signal_definition(
        support,
        data,
        _context(),
        JiraConnector.describe_signal_schema(),
        scopes,
    )

    assert [finding.title for finding in scrum_findings] == ["SCRUM-1 - Stale sprint work"]
    assert [finding.title for finding in kanban_findings] == ["KAN-1 - Aging kanban work"]
    assert [finding.title for finding in support_findings] == ["SUP-1 - Open support ticket"]


def test_preview_reasons_match_report_reasons() -> None:
    signal = _signal(
        "Support open longer than 3 days",
        "support-scope",
        "project",
        "age_since_created",
        {"amount": 3, "unit": "days"},
    )
    data = _data()
    report_findings = evaluate_signal_definition(
        signal,
        data,
        _context(),
        JiraConnector.describe_signal_schema(),
        _scopes(),
    )
    preview = preview_signal_definition(
        signal,
        data,
        _context(),
        JiraConnector.describe_signal_schema(),
        _scopes(),
    )

    assert preview["samples"][0]["reason"] == report_findings[0].reason


def test_template_import_mapping_expectations_are_represented() -> None:
    public_template_needs_mapping = {
        "export_type": "public_template",
        "templates": [{"key": "support-open", "required_scope_capabilities": ["statuses"]}],
    }
    private_backup_restores_mapping = {
        "export_type": "private_backup",
        "signals": [{"target_scopes": [{"scope_id": "support-scope"}]}],
    }

    assert public_template_needs_mapping["templates"][0]["required_scope_capabilities"] == [
        "statuses"
    ]
    assert private_backup_restores_mapping["signals"][0]["target_scopes"][0]["scope_id"] in {
        scope.scope_id for scope in _scopes()
    }


def _signal(
    name: str,
    scope_id: str,
    scope_type: str,
    field: str,
    value: dict[str, object],
) -> SignalDefinition:
    return SignalDefinition(
        name=name,
        entity_type="issue",
        target_scopes=[
            SignalTargetScope(connector_id="jira-main", scope_id=scope_id, scope_type=scope_type)
        ],
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is", "value": "in_progress"},
                {"field": field, "operator": "greater_than", "value": value},
            ],
        },
        report_settings=ReportSettings(severity="warning", category="uat"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _scopes() -> list[ScopeDescriptor]:
    return [
        ScopeDescriptor(
            connector_id="jira-main",
            scope_id="scrum-scope",
            scope_type="board",
            name="Scrum Board",
            external_ref={"type": "jira_board", "id": "scrum-board"},
            capabilities=("sprint", "statuses", "labels"),
        ),
        ScopeDescriptor(
            connector_id="jira-main",
            scope_id="kanban-scope",
            scope_type="board",
            name="Kanban Board",
            external_ref={"type": "jira_board", "id": "kanban-board"},
            capabilities=("kanban", "statuses", "labels"),
        ),
        ScopeDescriptor(
            connector_id="jira-main",
            scope_id="support-scope",
            scope_type="project",
            name="Support Project",
            external_ref={"type": "jira_project", "id": "support-project", "key": "SUP"},
            capabilities=("statuses", "labels"),
        ),
    ]


def _data() -> SignalData:
    project = Project(
        id=PROJECT_ID,
        source=Source.JIRA,
        external_id="product-project",
        key="PROD",
        name="Product",
    )
    kanban_project = Project(
        id=KANBAN_PROJECT_ID,
        source=Source.JIRA,
        external_id="kanban-project",
        key="KAN",
        name="Kanban",
    )
    support_project = Project(
        id=SUPPORT_PROJECT_ID,
        source=Source.JIRA,
        external_id="support-project",
        key="SUP",
        name="Support",
    )
    scrum_board = Board(
        id=SCRUM_BOARD_ID,
        source=Source.JIRA,
        external_id="scrum-board",
        project_id=project.id,
        name="Scrum Board",
        type=BoardType.SCRUM,
    )
    kanban_board = Board(
        id=KANBAN_BOARD_ID,
        source=Source.JIRA,
        external_id="kanban-board",
        project_id=kanban_project.id,
        name="Kanban Board",
        type=BoardType.KANBAN,
    )
    active_sprint = Sprint(
        id=SPRINT_ID,
        source=Source.JIRA,
        external_id="sprint-1",
        board_id=scrum_board.id,
        name="Sprint 1",
        state=SprintState.ACTIVE,
        start_date=NOW - timedelta(days=4),
        end_date=NOW + timedelta(days=6),
    )
    return SignalData(
        report_id=uuid4(),
        projects=(project, kanban_project, support_project),
        boards=(scrum_board, kanban_board),
        sprints=(active_sprint,),
        workitems=(
            _workitem(
                "SCRUM-1", "Stale sprint work", project.id, NOW - timedelta(days=8), SPRINT_ID
            ),
            _workitem(
                "KAN-1",
                "Aging kanban work",
                kanban_project.id,
                NOW - timedelta(days=14),
                None,
            ),
            _workitem(
                "SUP-1", "Open support ticket", support_project.id, NOW - timedelta(days=5), None
            ),
        ),
    )


def _workitem(
    key: str,
    title: str,
    project_id: UUID,
    created_at: datetime,
    sprint_id: UUID | None,
) -> WorkItem:
    sprint_ids = [sprint_id] if sprint_id is not None else []
    return WorkItem(
        source=Source.JIRA,
        external_id=key,
        project_id=project_id,
        key=key,
        type=WorkItemType.STORY,
        title=title,
        status="In Progress",
        status_category=StatusCategory.IN_PROGRESS,
        created_at=created_at,
        updated_at=created_at,
        sprint_ids=sprint_ids,
        current_sprint_id=sprint_id,
    )


def _context() -> EvaluationContext:
    team = TeamProfile(
        name="UAT Jira team",
        project_ids=[PROJECT_ID, SUPPORT_PROJECT_ID],
        repository_ids=[],
        created_at=NOW,
        updated_at=NOW,
    )
    return EvaluationContext(
        now=NOW,
        team=team,
        window=EvaluationWindow(
            window_type=WindowType.DATE_RANGE,
            start=NOW - timedelta(days=30),
            end=NOW,
            team_profile_id=team.id,
        ),
    )
