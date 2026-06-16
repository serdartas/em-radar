from collections.abc import AsyncIterator
from typing import ClassVar

from fastapi.testclient import TestClient

from em_radar_core.connectors import Capabilities, ConnectionTestResult, WorkItemScope
from em_radar_core.models import (
    Board,
    BoardType,
    EvaluationWindow,
    Project,
    Source,
    Sprint,
    SprintState,
    WorkItem,
)


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
        return
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


def test_jira_active_sprint_report_run(api_client: TestClient, monkeypatch) -> None:
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
