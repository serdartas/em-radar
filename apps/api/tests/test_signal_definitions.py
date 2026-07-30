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
        "enabled": True,
        "origin": "user_created",
        "template_key": None,
    }


def test_signal_can_be_created_and_enabled_without_scope(api_client: TestClient) -> None:
    response = api_client.post("/api/signal-definitions", json=_definition_payload())

    assert response.status_code == 201
    created = response.json()
    assert created["enabled"] is True
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


def test_version_increments_on_update(api_client: TestClient) -> None:
    created = api_client.post("/api/signal-definitions", json=_definition_payload()).json()

    update_response = api_client.patch(
        f"/api/signal-definitions/{created['id']}",
        json={"description": "Updated description."},
    )

    assert update_response.status_code == 200
    assert update_response.json()["version"] == created["version"] + 1


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
