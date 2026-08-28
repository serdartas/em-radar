from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.repositories.source_connections import create_source_connection
from em_radar_api.source_connections import ConnectorName, SourceConnectionCreate
from em_radar_api.tables import EvaluationWindowTable
from em_radar_core.models import WindowType


def test_team_profile_crud_supports_multiple_working_modes(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        connection = create_source_connection(
            session,
            SourceConnectionCreate(
                name="Jira prod",
                connector_name=ConnectorName.JIRA,
            ),
        )

    scrum_response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [str(connection.id)],
            "working_mode": "scrum",
            "sprint_length_days": 14,
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
            "working_mode": "kanban",
            "sprint_length_days": 14,
        },
    )

    assert response.status_code == 422


def test_caller_supplied_connection_ids_are_ignored(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    # connection_ids is server-derived from scope_ids + code_connection_id; any value sent
    # by the caller is ignored, so even a non-existent ID does not cause a 422.
    response = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "connection_ids": [str(uuid4())],
        },
    )

    assert response.status_code == 201
    # No scopes and no code_connection_id → derived connection_ids is empty.
    assert response.json()["connection_ids"] == []


def test_team_referenced_by_evaluation_window_cannot_be_deleted(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    created = api_client.post(
        "/api/teams",
        json={
            "name": "Platform",
            "working_mode": "scrum",
            "sprint_length_days": 14,
        },
    )
    assert created.status_code == 201
    team = created.json()

    with session_factory() as session:
        now = datetime.now(timezone.utc)
        session.add(
            EvaluationWindowTable(
                window_type=WindowType.DATE_RANGE,
                start=now,
                end=now,
                team_profile_id=UUID(team["id"]),
            )
        )
        session.commit()

    response = api_client.delete(f"/api/teams/{team['id']}")

    assert response.status_code == 409
    assert response.json()["detail"] == "team is referenced by an evaluation window"
    assert api_client.get(f"/api/teams/{team['id']}").status_code == 200


def test_team_profile_omits_vestigial_id_arrays(api_client: TestClient) -> None:
    """project_ids / board_ids / repository_ids are absent from both create payload and response."""
    response = api_client.post(
        "/api/teams",
        json={"name": "Clean team", "working_mode": "scrum", "sprint_length_days": 14},
    )
    assert response.status_code == 201
    body = response.json()

    assert "project_ids" not in body
    assert "board_ids" not in body
    assert "repository_ids" not in body

    read_body = api_client.get(f"/api/teams/{body['id']}").json()
    assert "project_ids" not in read_body
    assert "board_ids" not in read_body
    assert "repository_ids" not in read_body
