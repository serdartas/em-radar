from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.repositories.source_connections import create_source_connection
from em_radar_api.source_connections import ConnectorName, SourceConnectionCreate


def test_team_profile_crud_supports_multiple_working_modes(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    project_id = uuid4()
    board_id = uuid4()
    repository_id = uuid4()
    with session_factory() as session:
        connection = create_source_connection(
            session,
            SourceConnectionCreate(
                connector_name=ConnectorName.DEMO,
                selected_project_ids=[project_id],
                selected_board_ids=[board_id],
                selected_repository_ids=[repository_id],
            ),
        )

    scrum_response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [str(connection.id)],
            "project_ids": [str(project_id)],
            "board_ids": [str(board_id)],
            "repository_ids": [str(repository_id)],
            "working_mode": "scrum",
            "sprint_length_days": 14,
            "member_user_keys": ["jira:alice"],
        },
    )
    assert scrum_response.status_code == 201
    scrum = scrum_response.json()

    kanban_response = api_client.post(
        "/api/teams",
        json={
            "name": "Operations",
            "description": "Production operations",
            "connection_ids": [str(connection.id)],
            "project_ids": [str(project_id)],
            "repository_ids": [],
            "working_mode": "kanban",
        },
    )
    assert kanban_response.status_code == 201
    kanban = kanban_response.json()
    assert kanban["sprint_length_days"] is None

    assert api_client.get(f"/api/teams/{scrum['id']}").json() == scrum
    assert [team["id"] for team in api_client.get("/api/teams").json()] == [
        scrum["id"],
        kanban["id"],
    ]

    patch_response = api_client.patch(
        f"/api/teams/{scrum['id']}",
        json={"name": "Platform Engineering", "sprint_length_days": 7},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["name"] == "Platform Engineering"
    assert patched["sprint_length_days"] == 7
    assert patched["updated_at"] >= scrum["updated_at"]

    invalid_patch = api_client.patch(
        f"/api/teams/{scrum['id']}",
        json={"working_mode": "kanban"},
    )
    assert invalid_patch.status_code == 422

    assert api_client.delete(f"/api/teams/{kanban['id']}").status_code == 204
    assert api_client.get(f"/api/teams/{kanban['id']}").status_code == 404
    assert [team["id"] for team in api_client.get("/api/teams").json()] == [scrum["id"]]


def test_kanban_team_rejects_non_null_sprint_length(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/teams",
        json={
            "name": "Operations",
            "project_ids": [],
            "repository_ids": [],
            "working_mode": "kanban",
            "sprint_length_days": 14,
        },
    )

    assert response.status_code == 422


def test_team_scope_ids_must_belong_to_existing_connections(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [str(uuid4())],
            "project_ids": [str(uuid4())],
            "repository_ids": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "connection_ids must reference existing connections"

    with session_factory() as session:
        connection = create_source_connection(
            session,
            SourceConnectionCreate(
                connector_name=ConnectorName.JIRA,
                selected_project_ids=[uuid4()],
            ),
        )

    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [str(connection.id)],
            "project_ids": [str(uuid4())],
            "repository_ids": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "project_ids must reference the selected connections"


def test_team_referenced_by_evaluation_window_cannot_be_deleted(api_client: TestClient) -> None:
    assert api_client.post("/api/reports/run", json={"connector": "demo"}).status_code == 200
    team = api_client.get("/api/teams").json()[0]

    response = api_client.delete(f"/api/teams/{team['id']}")

    assert response.status_code == 409
    assert response.json()["detail"] == "team is referenced by an evaluation window"
    assert api_client.get(f"/api/teams/{team['id']}").status_code == 200
