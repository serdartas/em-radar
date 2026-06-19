from collections.abc import AsyncIterator
from typing import ClassVar
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.repositories.source_connections import create_source_connection
from em_radar_api.source_connections import ConnectorName, SourceConnectionCreate
from em_radar_core.connectors import Capabilities, ConnectionTestResult, WorkItemScope
from em_radar_core.models import (
    Board,
    BoardType,
    EvaluationWindow,
    Project,
    Source,
    Sprint,
    WorkItem,
)


class JiraScopeConnector:
    name: ClassVar[str] = "jira"
    display_name: ClassVar[str] = "Jira"
    config_schema: ClassVar[dict[str, object]] = {"type": "object"}
    min_model_version: ClassVar[int] = 1

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config

    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, detail="Connected")

    @classmethod
    def describe_capabilities(cls) -> Capabilities:
        del cls
        return Capabilities(provides_workitems=True, provides_sprints=True)

    async def close(self) -> None:
        pass

    async def list_projects(self) -> list[Project]:
        return [
            Project(
                id=UUID("0ec5b40d-a2a3-4b6d-9d13-5df115ad84d7"),
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
                id=UUID("9c27fca3-597b-44fe-9ed8-0796dfed867a"),
                source=Source.JIRA,
                external_id="20000",
                project_id=UUID("0ec5b40d-a2a3-4b6d-9d13-5df115ad84d7"),
                name="Platform Scrum",
                type=BoardType.SCRUM,
            ),
            Board(
                id=UUID("145e40d5-06d9-49ca-96c4-f41724ae1ef6"),
                source=Source.JIRA,
                external_id="20001",
                project_id=UUID("0ec5b40d-a2a3-4b6d-9d13-5df115ad84d7"),
                name="Platform Kanban",
                type=BoardType.KANBAN,
            ),
        ]

    async def list_sprints(self, board_id: str) -> list[Sprint]:
        del board_id
        return []

    async def fetch_workitems(
        self,
        scope: WorkItemScope,
        window: EvaluationWindow,
    ) -> AsyncIterator[WorkItem]:
        del scope, window
        if False:
            yield


def test_scope_definition_crud_and_team_scope_ids(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        connection = create_source_connection(
            session,
            SourceConnectionCreate(connector_name=ConnectorName.JIRA),
        )

    create_response = api_client.post(
        "/api/scopes",
        json={
            "connection_id": str(connection.id),
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
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["connection_id"] == str(connection.id)
    assert created["scope_type"] == "board"
    assert created["capabilities"] == ["sprint", "statuses", "labels"]
    assert "config" not in created

    assert api_client.get("/api/scopes").json() == [created]
    assert api_client.get(f"/api/scopes?connection_id={connection.id}").json() == [created]
    assert api_client.get(f"/api/scopes/{created['id']}").json() == created

    patch_response = api_client.patch(
        f"/api/scopes/{created['id']}",
        json={"name": "Platform Board", "capabilities": ["sprint", "statuses"]},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["name"] == "Platform Board"
    assert patched["capabilities"] == ["sprint", "statuses"]
    assert patched["updated_at"] >= created["updated_at"]

    team_response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [str(connection.id)],
            "scope_ids": [created["id"]],
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    )
    assert team_response.status_code == 201
    assert team_response.json()["scope_ids"] == [created["id"]]

    delete_response = api_client.delete(f"/api/scopes/{created['id']}")
    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == "scope definition is referenced by a team"


def test_scope_definitions_validate_connection_and_credentials(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/scopes",
        json={
            "connection_id": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
            "name": "Missing",
            "scope_type": "project",
            "external_ref": {"type": "jira_project", "id": "10000", "key": "PLAT"},
            "capabilities": ["statuses"],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "connection_id must reference an existing connection"

    connection_response = api_client.post(
        "/api/connections",
        json={"connector_name": "jira", "config": {"token": "jira-token-123456789"}},
    )
    assert connection_response.status_code == 201

    credential_response = api_client.post(
        "/api/scopes",
        json={
            "connection_id": connection_response.json()["id"],
            "name": "Leaky",
            "scope_type": "project",
            "external_ref": {"type": "jira_project", "id": "10000", "token": "secret"},
            "capabilities": ["statuses"],
        },
    )
    assert credential_response.status_code == 422
    assert credential_response.json()["detail"] == "external_ref must not contain credentials"

    variant_response = api_client.post(
        "/api/scopes",
        json={
            "connection_id": connection_response.json()["id"],
            "name": "Leaky Variant",
            "scope_type": "project",
            "external_ref": {
                "type": "jira_project",
                "id": "10001",
                "apiKey": "secret",
                "access_token": "secret",
            },
            "capabilities": ["statuses"],
        },
    )
    assert variant_response.status_code == 422
    assert variant_response.json()["detail"] == "external_ref must not contain credentials"


def test_scope_connection_cannot_move_when_referenced_by_team(api_client: TestClient) -> None:
    first_connection_response = api_client.post(
        "/api/connections",
        json={"connector_name": "jira", "config": {}},
    )
    second_connection_response = api_client.post(
        "/api/connections",
        json={"connector_name": "jira", "config": {}},
    )
    assert first_connection_response.status_code == 201
    assert second_connection_response.status_code == 201

    scope_response = api_client.post(
        "/api/scopes",
        json={
            "connection_id": first_connection_response.json()["id"],
            "name": "Custom Jira Scope",
            "scope_type": "custom",
            "external_ref": {"type": "custom", "id": "scope-1"},
            "capabilities": ["statuses"],
        },
    )
    assert scope_response.status_code == 201
    team_response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [first_connection_response.json()["id"]],
            "scope_ids": [scope_response.json()["id"]],
            "working_mode": "kanban",
        },
    )
    assert team_response.status_code == 201

    move_response = api_client.patch(
        f"/api/scopes/{scope_response.json()['id']}",
        json={"connection_id": second_connection_response.json()["id"]},
    )
    assert move_response.status_code == 409
    assert move_response.json()["detail"] == "scope definition is referenced by a team"


def test_connection_connector_name_cannot_change_when_scopes_reference_it(
    api_client: TestClient,
) -> None:
    connection_response = api_client.post(
        "/api/connections",
        json={"connector_name": "jira", "config": {}},
    )
    assert connection_response.status_code == 201
    scope_response = api_client.post(
        "/api/scopes",
        json={
            "connection_id": connection_response.json()["id"],
            "name": "Platform",
            "scope_type": "project",
            "external_ref": {"type": "jira_project", "id": "10000", "key": "PLAT"},
            "capabilities": ["statuses"],
        },
    )
    assert scope_response.status_code == 201

    response = api_client.patch(
        f"/api/connections/{connection_response.json()['id']}",
        json={"connector_name": "gitlab"},
    )
    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "source connection connector_name cannot change while scopes reference it"
    )


def test_jira_project_and_board_listing_populates_scope_definitions(
    api_client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "em_radar_api.connector_registry._connector_types",
        lambda: [JiraScopeConnector],
    )
    connection_response = api_client.post(
        "/api/connections",
        json={"connector_name": "jira", "config": {}},
    )
    assert connection_response.status_code == 201
    connection_id = connection_response.json()["id"]

    projects_response = api_client.get(f"/api/connections/{connection_id}/projects")
    assert projects_response.status_code == 200
    assert [project["external_id"] for project in projects_response.json()] == ["10000"]

    boards_response = api_client.get(f"/api/connections/{connection_id}/projects/10000/boards")
    assert boards_response.status_code == 200
    assert [board["external_id"] for board in boards_response.json()] == ["20000", "20001"]

    scopes_response = api_client.get(f"/api/scopes?connection_id={connection_id}")
    assert scopes_response.status_code == 200
    scopes = scopes_response.json()
    assert [(scope["scope_type"], scope["external_ref"]["id"]) for scope in scopes] == [
        ("project", "10000"),
        ("board", "20000"),
        ("board", "20001"),
    ]
    assert scopes[0]["external_ref"] == {
        "type": "jira_project",
        "id": "10000",
        "key": "PLAT",
        "name": "Platform",
    }
    assert scopes[1]["capabilities"] == ["sprint", "statuses", "labels"]
    assert scopes[2]["capabilities"] == ["kanban", "statuses", "labels"]

    repeat_response = api_client.get(f"/api/connections/{connection_id}/projects")
    assert repeat_response.status_code == 200
    assert len(api_client.get(f"/api/scopes?connection_id={connection_id}").json()) == 3
