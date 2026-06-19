from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, tzinfo
from typing import ClassVar
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_core.connectors import Capabilities, ConnectionTestResult, WorkItemScope
from em_radar_core.models import (
    Board,
    BoardType,
    EntityType,
    EvaluationWindow,
    Project,
    Source,
    Sprint,
    SprintState,
    StatusCategory,
    Transition,
    WorkItem,
    WorkItemType,
)
from em_radar_api.tables import EvaluationWindowTable, UserTable

_REPORT_STARTED_AT = datetime(2026, 6, 17, 12, tzinfo=UTC)


class FrozenReportDateTime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        if tz is None:
            return _REPORT_STARTED_AT.replace(tzinfo=None)
        return _REPORT_STARTED_AT.astimezone(tz)


class JiraTestConnector:
    name: ClassVar[str] = "jira"
    display_name: ClassVar[str] = "Jira"
    config_schema: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "base_url": {"type": "string"},
            "token": {"type": "string", "minLength": 20},
        },
        "required": ["base_url", "token"],
        "additionalProperties": False,
    }
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            ok=True,
            detail="Connected",
            user_display_name="Ada Lovelace",
            permissions=["read"],
        )

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities()

    async def close(self) -> None:
        pass

    async def list_projects(self) -> list[Project]:
        return [
            Project(
                id="4c7a2c4f-e62f-4a78-bf6f-81f0a2a08826",
                source=Source.JIRA,
                external_id="10000",
                key="PLAT",
                name="Platform",
            )
        ]

    async def list_boards(self, project_id: str) -> list[Board]:
        assert project_id == "10000"
        return [
            Board(
                id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                source=Source.JIRA,
                external_id="20000",
                project_id="4c7a2c4f-e62f-4a78-bf6f-81f0a2a08826",
                name="Platform Scrum",
                type=BoardType.SCRUM,
            )
        ]

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        assert board_id == "20000"
        return [
            Sprint(
                id="45cdfd02-9cde-4c65-a618-7728fc9fb495",
                source=Source.JIRA,
                external_id="30000",
                board_id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                name="Platform Sprint 12",
                state=SprintState.ACTIVE,
            )
        ]

    async def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]:
        del scope, window
        yield WorkItem(
            id=UUID("80a0d17d-5fb4-46c4-bc3a-e8b4f85c9cb0"),
            source=Source.JIRA,
            external_id="PLAT-1",
            project_id=UUID("4c7a2c4f-e62f-4a78-bf6f-81f0a2a08826"),
            key="PLAT-1",
            type=WorkItemType.TASK,
            title="Assigned Jira story",
            status="In Progress",
            status_category=StatusCategory.IN_PROGRESS,
            assignee_id=UUID("7de90589-74cc-4f11-a205-17d3bcd60735"),
            reporter_id=UUID("b60ef25e-379e-446d-b6d7-f7610f8ab6a1"),
            sprint_ids=[UUID("45cdfd02-9cde-4c65-a618-7728fc9fb495")],
            current_sprint_id=UUID("45cdfd02-9cde-4c65-a618-7728fc9fb495"),
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=_REPORT_STARTED_AT,
        )

    async def fetch_transitions(
        self,
        entity_type: str,
        entity_external_ids: list[str],
    ) -> AsyncIterator[Transition]:
        assert entity_type == "workitem"
        assert entity_external_ids == ["PLAT-1"]
        yield Transition(
            entity_type=EntityType.WORKITEM,
            entity_id=UUID("80a0d17d-5fb4-46c4-bc3a-e8b4f85c9cb0"),
            from_status="To Do",
            to_status="In Progress",
            from_status_category=StatusCategory.TODO,
            to_status_category=StatusCategory.IN_PROGRESS,
            actor_id=UUID("ef482427-5e1b-45fd-bc1c-832e887116dd"),
            occurred_at=datetime(2026, 6, 2, tzinfo=UTC),
        )


class JiraKanbanTestConnector(JiraTestConnector):
    async def list_boards(self, project_id: str) -> list[Board]:
        assert project_id == "10000"
        return [
            Board(
                id="54111f22-2a3a-4cb4-8c8a-4fc0942dba49",
                source=Source.JIRA,
                external_id="20000",
                project_id="4c7a2c4f-e62f-4a78-bf6f-81f0a2a08826",
                name="Platform Kanban",
                type=BoardType.KANBAN,
            )
        ]

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        assert board_id == "20000"
        return []

    async def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]:
        del scope
        assert window.window_type == "date_range"
        assert window.start == _REPORT_STARTED_AT - timedelta(days=14)
        assert window.end == _REPORT_STARTED_AT
        if False:
            yield

    async def fetch_transitions(
        self,
        entity_type: str,
        entity_external_ids: list[str],
    ) -> AsyncIterator[Transition]:
        del entity_type, entity_external_ids
        if False:
            yield


def test_source_connection_routes_crud_test_and_preserve_omitted_config(
    api_client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    created_response = api_client.post(
        "/api/connections",
        json={
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["config"] == {
        "base_url": "https://demo.invalid",
        "token": "****6789",
    }

    assert api_client.get("/api/connections").json() == [created]

    test_response = api_client.post(f"/api/connections/{created['id']}/test")
    assert test_response.status_code == 200
    assert test_response.json() == {
        "ok": True,
        "detail": "Connected",
        "user_display_name": "Ada Lovelace",
        "permissions": ["read"],
    }

    updated_response = api_client.patch(
        f"/api/connections/{created['id']}",
        json={"config": {"base_url": "https://updated.invalid"}},
    )
    assert updated_response.status_code == 200
    assert updated_response.json()["config"] == {
        "base_url": "https://updated.invalid",
        "token": "****6789",
    }

    assert api_client.delete(f"/api/connections/{created['id']}").status_code == 204
    assert api_client.get("/api/connections").json() == []


def test_source_connection_draft_test_returns_token_free_failure(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/connections/test",
        json={"connector_name": "demo", "config": {"unexpected": "secret-token"}},
    )

    assert response.status_code == 200
    assert not response.json()["ok"]
    assert "secret-token" not in response.json()["detail"]


def test_source_connection_jira_list_routes(api_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    created = api_client.post(
        "/api/connections",
        json={
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    ).json()

    projects = api_client.get(f"/api/connections/{created['id']}/projects")
    boards = api_client.get(f"/api/connections/{created['id']}/projects/10000/boards")
    sprints = api_client.get(f"/api/connections/{created['id']}/boards/20000/sprints")

    assert projects.status_code == 200
    assert projects.json()[0]["key"] == "PLAT"
    assert boards.status_code == 200
    assert boards.json()[0]["type"] == "scrum"
    assert sprints.status_code == 200
    assert sprints.json()[0]["state"] == "active"


def test_jira_active_sprint_report_run_persists_user_references(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)
    created = api_client.post(
        "/api/connections",
        json={
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    ).json()

    response = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "jira": {
                "connection_id": created["id"],
                "project_external_id": "10000",
                "board_external_id": "20000",
                "working_mode": "scrum",
                "sprint_length_days": 14,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["findings"] == []

    with session_factory() as session:
        users = session.exec(select(UserTable).order_by(UserTable.external_id)).all()

    assert {user.external_id for user in users} == {
        "7de90589-74cc-4f11-a205-17d3bcd60735",
        "b60ef25e-379e-446d-b6d7-f7610f8ab6a1",
        "ef482427-5e1b-45fd-bc1c-832e887116dd",
    }


def test_jira_report_run_evaluates_saved_signal_definitions(
    api_client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)
    created = api_client.post(
        "/api/connections",
        json={
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    ).json()
    scope = api_client.post(
        "/api/scopes",
        json={
            "connection_id": created["id"],
            "name": "Platform Scrum",
            "scope_type": "board",
            "external_ref": {
                "type": "jira_board",
                "id": "20000",
                "key": None,
                "name": "Platform Scrum",
            },
            "capabilities": ["sprint", "statuses", "labels"],
        },
    ).json()
    definition = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Scoped stale Jira work",
            "entity_type": "issue",
            "target_scopes": [
                {
                    "connector_id": created["id"],
                    "scope_id": scope["id"],
                    "scope_type": "board",
                }
            ],
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [
                    {
                        "field": "age_in_current_status",
                        "operator": "greater_than",
                        "value": {"amount": 3, "unit": "days"},
                    }
                ],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "enabled": True,
            "origin": "user_created",
        },
    ).json()

    response = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "jira": {
                "connection_id": created["id"],
                "project_external_id": "10000",
                "board_external_id": "20000",
                "working_mode": "scrum",
                "sprint_length_days": 14,
            },
        },
    )

    assert response.status_code == 200
    findings = response.json()["findings"]
    assert any(finding["signal_id"] == definition["id"] for finding in findings)
    assert (
        response.json()["signal_pack_snapshot"]["signal_definitions"][0]["id"] == definition["id"]
    )


def test_jira_kanban_report_uses_date_range_without_active_sprint(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraKanbanTestConnector],
    )
    monkeypatch.setattr("em_radar_api.routers.reports.datetime", FrozenReportDateTime)
    created = api_client.post(
        "/api/connections",
        json={
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    ).json()

    response = api_client.post(
        "/api/reports/run",
        json={
            "connector": "jira",
            "jira": {
                "connection_id": created["id"],
                "project_external_id": "10000",
                "board_external_id": "20000",
                "working_mode": "kanban",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"

    with session_factory() as session:
        window = session.get(
            EvaluationWindowTable,
            UUID(response.json()["evaluation_window_id"]),
        )

    assert window is not None
    assert window.window_type == "date_range"
    assert window.start == (_REPORT_STARTED_AT - timedelta(days=14)).replace(tzinfo=None)
    assert window.end == _REPORT_STARTED_AT.replace(tzinfo=None)
