from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect

from em_radar_api.db import DATABASE_PATH_ENV, create_db_engine

REPO_ROOT = Path(__file__).parents[3]


def _definition_payload(name: str = "Stale platform work") -> dict[str, object]:
    return {
        "name": name,
        "description": "Finds stale Jira issues.",
        "entity_type": "issue",
        "expression": {
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "status_category", "operator": "is", "value": "in_progress"}],
        },
        "report_settings": {"severity": "warning", "category": "flow"},
        "origin": "user_created",
        "template_key": None,
    }


def test_signal_can_be_created_without_scope(api_client: TestClient) -> None:
    response = api_client.post("/api/signal-definitions", json=_definition_payload())

    assert response.status_code == 201
    created = response.json()
    assert "enabled" not in created
    assert "version" not in created
    assert "target_scopes" not in created


def test_signal_response_omits_target_scopes(api_client: TestClient) -> None:
    created = api_client.post("/api/signal-definitions", json=_definition_payload()).json()

    fetched = api_client.get(f"/api/signal-definitions/{created['id']}").json()

    assert "target_scopes" not in fetched
    assert "target_scopes" not in api_client.get("/api/signal-definitions").json()[0]


def test_duplicate_signal_names_are_rejected(api_client: TestClient) -> None:
    response = api_client.post("/api/signal-definitions", json=_definition_payload())
    assert response.status_code == 201

    duplicate = api_client.post("/api/signal-definitions", json=_definition_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "signal name must be unique"


def test_signal_updated_at_changes_on_update(api_client: TestClient) -> None:
    created = api_client.post("/api/signal-definitions", json=_definition_payload()).json()

    update_response = api_client.patch(
        f"/api/signal-definitions/{created['id']}",
        json={"description": "Updated description."},
    )

    assert update_response.status_code == 200
    assert update_response.json()["updated_at"] is not None


def test_update_signal_definition_overwrites_in_place(api_client: TestClient) -> None:
    created = api_client.post("/api/signal-definitions", json=_definition_payload()).json()
    original_id = created["id"]

    updated_expression = {
        "type": "group",
        "operator": "any",
        "conditions": [
            {"field": "status_category", "operator": "is_not", "value": "done"},
            {"field": "age_in_current_status", "operator": "greater_than", "value": 7},
        ],
    }
    update_payload = {
        "name": "Renamed signal",
        "description": "Updated description.",
        "expression": updated_expression,
        "report_settings": {"severity": "critical", "category": "hygiene"},
    }

    response = api_client.patch(f"/api/signal-definitions/{original_id}", json=update_payload)

    assert response.status_code == 200
    result = response.json()
    # Same record (no new version) — id unchanged
    assert result["id"] == original_id
    assert result["name"] == "Renamed signal"
    assert result["description"] == "Updated description."
    assert result["expression"]["operator"] == "any"
    assert len(result["expression"]["conditions"]) == 2
    assert result["report_settings"]["severity"] == "critical"
    assert result["report_settings"]["category"] == "hygiene"

    # Confirm only one definition exists (no duplicate created)
    all_defs = api_client.get("/api/signal-definitions").json()
    assert len(all_defs) == 1
    assert all_defs[0]["id"] == original_id


def test_update_signal_definition_returns_404_for_unknown_id(api_client: TestClient) -> None:
    from uuid import uuid4

    response = api_client.patch(
        f"/api/signal-definitions/{uuid4()}",
        json={"name": "Does not exist"},
    )

    assert response.status_code == 404


def test_migration_drops_target_scopes_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "drop-scopes.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))
    config = Config(REPO_ROOT / "alembic.ini")

    command.upgrade(config, "head")

    columns = {
        column["name"]
        for column in inspect(create_db_engine(database_path)).get_columns("signal_definition")
    }
    assert "target_scopes" not in columns
    assert "enabled" not in columns
    assert "version" not in columns
