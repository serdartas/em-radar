from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, tzinfo
from typing import ClassVar
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select

from em_radar_core.connectors import (
    Capabilities,
    ConnectionTestResult,
    ConnectorAuthError,
    ConnectorConfigError,
    ConnectorNotFoundError,
    ConnectorRateLimitedError,
    ConnectorTransientError,
    WorkItemScope,
)
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
        return Capabilities(
            provides_workitems=True,
            provides_sprints=True,
            provides_transitions=True,
        )

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


class JiraAuthErrorOnPickerConnector(JiraTestConnector):
    async def list_projects(self) -> list[Project]:
        raise ConnectorAuthError("token expired")

    async def list_boards(self, project_id: str) -> list[Board]:
        raise ConnectorAuthError("token expired")

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        raise ConnectorAuthError("token expired")


class JiraNotFoundErrorOnPickerConnector(JiraTestConnector):
    async def list_projects(self) -> list[Project]:
        raise ConnectorNotFoundError("project not found")

    async def list_boards(self, project_id: str) -> list[Board]:
        raise ConnectorNotFoundError("board not found")

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        raise ConnectorNotFoundError("board not found")


class JiraRateLimitedOnPickerConnector(JiraTestConnector):
    async def list_projects(self) -> list[Project]:
        raise ConnectorRateLimitedError("rate limited")

    async def list_boards(self, project_id: str) -> list[Board]:
        raise ConnectorRateLimitedError("rate limited")

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        raise ConnectorRateLimitedError("rate limited")


class JiraConfigErrorOnPickerConnector(JiraTestConnector):
    async def list_projects(self) -> list[Project]:
        raise ConnectorConfigError("bad config")

    async def list_boards(self, project_id: str) -> list[Board]:
        raise ConnectorConfigError("bad config")

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        raise ConnectorConfigError("bad config")


class JiraTransientErrorOnPickerConnector(JiraTestConnector):
    async def list_projects(self) -> list[Project]:
        raise ConnectorTransientError("Jira unreachable")

    async def list_boards(self, project_id: str) -> list[Board]:
        raise ConnectorTransientError("Jira unreachable")

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        raise ConnectorTransientError("Jira unreachable")


class JiraAuthErrorConnector(JiraTestConnector):
    async def test_connection(self) -> ConnectionTestResult:
        raise ConnectorAuthError("Jira authentication failed")


class JiraNotFoundErrorConnector(JiraTestConnector):
    async def test_connection(self) -> ConnectionTestResult:
        raise ConnectorNotFoundError("Jira endpoint was not found")


class JiraTransientErrorConnector(JiraTestConnector):
    async def test_connection(self) -> ConnectionTestResult:
        raise ConnectorTransientError("Failed to reach Jira")


def _create_jira_connection(api_client: TestClient, name: str = "Jira") -> str:
    return api_client.post(
        "/api/connections",
        json={
            "name": name,
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    ).json()["id"]


def _create_board_scope(api_client: TestClient, connection_id: str, capabilities: list[str]) -> str:
    return api_client.post(
        "/api/scopes",
        json={
            "connection_id": connection_id,
            "name": "Platform Scrum",
            "scope_type": "board",
            "external_ref": {"type": "jira_board", "id": "20000", "key": None},
            "capabilities": capabilities,
        },
    ).json()["id"]


def _create_jira_team(
    api_client: TestClient,
    connection_id: str,
    scope_id: str,
    working_mode: str,
    sprint_length_days: int | None = None,
    group_ids: list[str] | None = None,
) -> str:
    payload: dict[str, object] = {
        "name": f"Team {working_mode} {scope_id[:8]}",
        "connection_ids": [connection_id],
        "scope_ids": [scope_id],
        "working_mode": working_mode,
        "signal_config_group_ids": group_ids or [],
    }
    if sprint_length_days is not None:
        payload["sprint_length_days"] = sprint_length_days
    return api_client.post("/api/teams", json=payload).json()["id"]


def test_source_connection_test_maps_failures_to_error_codes(
    api_client: TestClient, monkeypatch
) -> None:
    cases = [
        (JiraAuthErrorConnector, "auth"),
        (JiraNotFoundErrorConnector, "not_found"),
        (JiraTransientErrorConnector, "transient"),
    ]
    for connector_type, expected_code in cases:
        monkeypatch.setattr(
            "em_radar_api.connector_registry._connector_types",
            lambda connector_type=connector_type: [connector_type],
        )
        response = api_client.post(
            "/api/connections/test",
            json={
                "connector_name": "jira",
                "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["code"] == expected_code


def test_source_connection_test_maps_invalid_config_to_config_code(
    api_client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    response = api_client.post(
        "/api/connections/test",
        json={
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "short"},
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["code"] == "config"


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
            "name": "Jira prod",
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["name"] == "Jira prod"
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
        "code": None,
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
        json={"connector_name": "jira", "config": {"unexpected": "secret-token"}},
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
            "name": "Jira prod",
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
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, ["sprint", "statuses", "labels"])
    team_id = _create_jira_team(api_client, connection_id, scope_id, "scrum", sprint_length_days=14)

    response = api_client.post(
        "/api/reports/run",
        json={"connector": "jira", "team_profile_id": team_id},
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
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, ["sprint", "statuses", "labels"])
    definition = api_client.post(
        "/api/signal-definitions",
        json={
            "name": "Scoped stale Jira work",
            "entity_type": "issue",
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
    group = api_client.post(
        "/api/signal-config-groups",
        json={"name": "Jira signals", "signal_ids": [definition["id"]]},
    ).json()
    team_id = _create_jira_team(
        api_client,
        connection_id,
        scope_id,
        "scrum",
        sprint_length_days=14,
        group_ids=[group["id"]],
    )
    response = api_client.post(
        "/api/reports/run",
        json={"connector": "jira", "team_profile_id": team_id},
    )

    assert response.status_code == 200
    findings = response.json()["findings"]
    assert any(finding["signal_id"] == definition["id"] for finding in findings)
    assert all(finding["signal_id"] != "stale-in-progress-work-item" for finding in findings)
    assert (
        response.json()["signal_pack_snapshot"]["signal_definitions"][0]["id"] == definition["id"]
    )


def test_signal_definition_preview_uses_persisted_jira_samples_and_warnings(
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
            "name": "Jira prod",
            "connector_name": "jira",
            "config": {"base_url": "https://demo.invalid", "token": "demo-token-123456789"},
        },
    ).json()
    board_scope = api_client.post(
        "/api/scopes",
        json={
            "connection_id": created["id"],
            "name": "Platform Scrum",
            "scope_type": "board",
            "external_ref": {"type": "jira_board", "id": "20000", "key": None},
            "capabilities": ["sprint", "statuses", "labels"],
        },
    ).json()
    project_scope = api_client.post(
        "/api/scopes",
        json={
            "connection_id": created["id"],
            "name": "Platform",
            "scope_type": "project",
            "external_ref": {"type": "jira_project", "id": "10000", "key": "PLAT"},
            "capabilities": ["statuses", "labels"],
        },
    ).json()
    team_id = _create_jira_team(
        api_client, created["id"], board_scope["id"], "scrum", sprint_length_days=14
    )
    api_client.post("/api/reports/run", json={"connector": "jira", "team_profile_id": team_id})

    response = api_client.post(
        "/api/signal-definitions/preview",
        params={"scope_ids": [board_scope["id"]]},
        json={
            "name": "Preview stale Jira work",
            "entity_type": "issue",
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
    )
    warning_response = api_client.post(
        "/api/signal-definitions/preview",
        params={"scope_ids": [project_scope["id"]]},
        json={
            "name": "Unsupported sprint field",
            "entity_type": "issue",
            "expression": {
                "type": "group",
                "operator": "all",
                "conditions": [{"field": "sprint_day", "operator": "is_after", "value": 1}],
            },
            "report_settings": {"severity": "warning", "category": "flow"},
            "enabled": True,
            "origin": "user_created",
        },
    )

    assert response.status_code == 200
    assert response.json()["match_count"] == 1
    assert response.json()["samples"][0]["item_key"] == "PLAT-1"
    assert "age_in_current_status" in response.json()["samples"][0]["reason"]
    assert warning_response.status_code == 200
    assert "requires scope capability" in warning_response.json()["warnings"][0]


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
    connection_id = _create_jira_connection(api_client)
    scope_id = _create_board_scope(api_client, connection_id, ["statuses", "labels"])
    team_id = _create_jira_team(api_client, connection_id, scope_id, "kanban")

    response = api_client.post(
        "/api/reports/run",
        json={"connector": "jira", "team_profile_id": team_id},
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


def test_source_connection_create_requires_name(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/connections",
        json={"connector_name": "jira", "config": {}},
    )
    assert response.status_code == 422


def test_source_connection_duplicate_name_rejected(api_client: TestClient) -> None:
    first = api_client.post(
        "/api/connections",
        json={"name": "Jira prod", "connector_name": "jira", "config": {}},
    )
    assert first.status_code == 201

    second = api_client.post(
        "/api/connections",
        json={"name": "Jira prod", "connector_name": "jira", "config": {}},
    )
    assert second.status_code == 422
    assert "Jira prod" in second.json()["detail"]


def test_source_connection_duplicate_name_rejected_on_patch(api_client: TestClient) -> None:
    api_client.post(
        "/api/connections",
        json={"name": "Jira A", "connector_name": "jira", "config": {}},
    )
    b = api_client.post(
        "/api/connections",
        json={"name": "Jira B", "connector_name": "jira", "config": {}},
    ).json()

    response = api_client.patch(f"/api/connections/{b['id']}", json={"name": "Jira A"})
    assert response.status_code == 422
    assert "Jira A" in response.json()["detail"]


def test_source_connection_selected_fields_absent_from_api(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/connections",
        json={"name": "Jira prod", "connector_name": "jira", "config": {}},
    )
    assert response.status_code == 201
    body = response.json()
    assert "selected_project_ids" not in body
    assert "selected_board_ids" not in body
    assert "selected_repository_ids" not in body
    assert "name" in body


def test_two_connections_same_connector_different_names_coexist(api_client: TestClient) -> None:
    r1 = api_client.post(
        "/api/connections",
        json={"name": "Jira tenant A", "connector_name": "jira", "config": {}},
    )
    r2 = api_client.post(
        "/api/connections",
        json={"name": "Jira tenant B", "connector_name": "jira", "config": {}},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["name"] == "Jira tenant A"
    assert r2.json()["name"] == "Jira tenant B"

    listed = api_client.get("/api/connections").json()
    assert len(listed) == 2
    names = {c["name"] for c in listed}
    assert names == {"Jira tenant A", "Jira tenant B"}


def test_source_connection_patch_null_name_returns_422(api_client: TestClient) -> None:
    connection = api_client.post(
        "/api/connections",
        json={"name": "Jira prod", "connector_name": "jira", "config": {}},
    ).json()

    response = api_client.patch(f"/api/connections/{connection['id']}", json={"name": None})
    assert response.status_code == 422


def test_source_connection_blank_name_returns_422(api_client: TestClient) -> None:
    response_empty = api_client.post(
        "/api/connections",
        json={"name": "", "connector_name": "jira", "config": {}},
    )
    assert response_empty.status_code == 422

    response_whitespace = api_client.post(
        "/api/connections",
        json={"name": "   ", "connector_name": "jira", "config": {}},
    )
    assert response_whitespace.status_code == 422


def test_source_connection_draft_test_works_without_name(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/connections/test",
        json={"connector_name": "jira", "config": {}},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "connector_class, expected_status",
    [
        (JiraAuthErrorOnPickerConnector, 401),
        (JiraNotFoundErrorOnPickerConnector, 404),
        (JiraRateLimitedOnPickerConnector, 429),
        (JiraConfigErrorOnPickerConnector, 422),
        (JiraTransientErrorOnPickerConnector, 502),
    ],
)
def test_picker_endpoints_map_connector_error_not_500(
    api_client: TestClient,
    monkeypatch,
    connector_class: type,
    expected_status: int,
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [connector_class],
    )
    connection_id = _create_jira_connection(api_client)

    projects_response = api_client.get(f"/api/connections/{connection_id}/projects")
    assert projects_response.status_code == expected_status
    assert "Traceback" not in projects_response.text
    assert "demo-token-123456789" not in projects_response.json()["detail"]

    boards_response = api_client.get(f"/api/connections/{connection_id}/projects/10000/boards")
    assert boards_response.status_code == expected_status
    assert "Traceback" not in boards_response.text
    assert "demo-token-123456789" not in boards_response.json()["detail"]

    sprints_response = api_client.get(f"/api/connections/{connection_id}/boards/20000/sprints")
    assert sprints_response.status_code == expected_status
    assert "Traceback" not in sprints_response.text
    assert "demo-token-123456789" not in sprints_response.json()["detail"]


def test_picker_listing_is_side_effect_free_and_connection_remains_deletable(
    api_client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraTestConnector],
    )
    connection_id = _create_jira_connection(api_client)

    assert api_client.get(f"/api/connections/{connection_id}/projects").status_code == 200
    assert (
        api_client.get(f"/api/connections/{connection_id}/projects/10000/boards").status_code == 200
    )
    assert (
        api_client.get(f"/api/connections/{connection_id}/boards/20000/sprints").status_code == 200
    )

    # No ScopeDefinition rows must have been created by picker reads.
    scopes = api_client.get(f"/api/scopes?connection_id={connection_id}")
    assert scopes.json() == []

    # The connection must be deletable because no accidental scope rows block it.
    assert api_client.delete(f"/api/connections/{connection_id}").status_code == 204
