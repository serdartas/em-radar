from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_api.db import DATABASE_PATH_ENV, create_db_engine
from em_radar_api.repositories.signal_definitions import create_signal_definition
from em_radar_api.signal_definitions import SignalDefinitionCreate

REPO_ROOT = Path(__file__).parents[3]


def _group_payload(**overrides: object) -> dict[str, object]:
    return {"name": "Backend signals", "description": "Signals for backend team", **overrides}


def _signal_payload(name: str = "Stale issue") -> dict[str, object]:
    return {
        "name": name,
        "entity_type": "issue",
        "target_scopes": [{"connector_id": "conn-1", "scope_id": "scope-1", "scope_type": "board"}],
        "expression": {
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "status_category", "operator": "is", "value": "in_progress"}],
        },
        "report_settings": {"severity": "warning", "category": "flow"},
        "enabled": True,
        "origin": "user_created",
    }


def _create_signal(session_factory: sessionmaker[Session], name: str = "Stale issue") -> str:
    with session_factory() as session:
        signal = create_signal_definition(session, SignalDefinitionCreate(**_signal_payload(name)))
    return str(signal.id)


class TestSignalConfigGroupCRUD:
    def test_create_group_without_signals(self, api_client: TestClient) -> None:
        response = api_client.post("/api/signal-config-groups", json=_group_payload())
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Backend signals"
        assert body["signal_ids"] == []
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_create_group_with_two_signal_ids(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig1 = _create_signal(session_factory, "Signal A")
        sig2 = _create_signal(session_factory, "Signal B")

        response = api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(signal_ids=[sig1, sig2]),
        )
        assert response.status_code == 201
        body = response.json()
        assert set(body["signal_ids"]) == {sig1, sig2}

    def test_same_signal_accepted_in_second_group(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig_id = _create_signal(session_factory)

        api_client.post("/api/signal-config-groups", json=_group_payload(signal_ids=[sig_id]))
        response = api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(name="Platform signals", signal_ids=[sig_id]),
        )
        assert response.status_code == 201

    def test_nonexistent_signal_id_is_rejected(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(signal_ids=[str(uuid4())]),
        )
        assert response.status_code == 422
        assert "signal_ids must reference existing signal definitions" in response.json()["detail"]

    def test_duplicate_group_name_is_rejected(self, api_client: TestClient) -> None:
        api_client.post("/api/signal-config-groups", json=_group_payload())
        response = api_client.post("/api/signal-config-groups", json=_group_payload())
        assert response.status_code == 409
        assert response.json()["detail"] == "group name must be unique"

    def test_list_returns_groups_ordered_by_name(self, api_client: TestClient) -> None:
        api_client.post("/api/signal-config-groups", json=_group_payload(name="Zebra team"))
        api_client.post("/api/signal-config-groups", json=_group_payload(name="Alpha team"))

        response = api_client.get("/api/signal-config-groups")
        assert response.status_code == 200
        names = [g["name"] for g in response.json()]
        assert names == sorted(names)

    def test_get_group_by_id(self, api_client: TestClient) -> None:
        created = api_client.post("/api/signal-config-groups", json=_group_payload()).json()

        response = api_client.get(f"/api/signal-config-groups/{created['id']}")
        assert response.status_code == 200
        assert response.json() == created

    def test_get_nonexistent_group_returns_404(self, api_client: TestClient) -> None:
        response = api_client.get(f"/api/signal-config-groups/{uuid4()}")
        assert response.status_code == 404

    def test_patch_group_name(self, api_client: TestClient) -> None:
        created = api_client.post("/api/signal-config-groups", json=_group_payload()).json()

        response = api_client.patch(
            f"/api/signal-config-groups/{created['id']}",
            json={"name": "Renamed signals"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed signals"
        assert response.json()["updated_at"] >= created["updated_at"]

    def test_patch_signal_ids_validates_existence(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        created = api_client.post("/api/signal-config-groups", json=_group_payload()).json()
        sig_id = _create_signal(session_factory)

        valid = api_client.patch(
            f"/api/signal-config-groups/{created['id']}",
            json={"signal_ids": [sig_id]},
        )
        assert valid.status_code == 200
        assert sig_id in valid.json()["signal_ids"]

        invalid = api_client.patch(
            f"/api/signal-config-groups/{created['id']}",
            json={"signal_ids": [str(uuid4())]},
        )
        assert invalid.status_code == 422

    def test_patch_signal_ids_null_returns_422_not_409(self, api_client: TestClient) -> None:
        created = api_client.post("/api/signal-config-groups", json=_group_payload()).json()
        response = api_client.patch(
            f"/api/signal-config-groups/{created['id']}",
            json={"signal_ids": None},
        )
        assert response.status_code == 422

    def test_patch_name_null_returns_422_not_409(self, api_client: TestClient) -> None:
        created = api_client.post("/api/signal-config-groups", json=_group_payload()).json()
        response = api_client.patch(
            f"/api/signal-config-groups/{created['id']}",
            json={"name": None},
        )
        assert response.status_code == 422

    def test_duplicate_signal_ids_in_create_are_rejected(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig_id = _create_signal(session_factory)
        response = api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(signal_ids=[sig_id, sig_id]),
        )
        assert response.status_code == 422
        assert "must not contain duplicates" in response.json()["detail"]

    def test_duplicate_signal_ids_in_patch_are_rejected(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        created = api_client.post("/api/signal-config-groups", json=_group_payload()).json()
        sig_id = _create_signal(session_factory)
        response = api_client.patch(
            f"/api/signal-config-groups/{created['id']}",
            json={"signal_ids": [sig_id, sig_id]},
        )
        assert response.status_code == 422
        assert "must not contain duplicates" in response.json()["detail"]

    def test_patch_nonexistent_group_returns_404(self, api_client: TestClient) -> None:
        response = api_client.patch(f"/api/signal-config-groups/{uuid4()}", json={"name": "X"})
        assert response.status_code == 404

    def test_patch_duplicate_name_returns_409(self, api_client: TestClient) -> None:
        api_client.post("/api/signal-config-groups", json=_group_payload(name="Alpha"))
        group_b = api_client.post(
            "/api/signal-config-groups", json=_group_payload(name="Beta")
        ).json()

        response = api_client.patch(
            f"/api/signal-config-groups/{group_b['id']}", json={"name": "Alpha"}
        )
        assert response.status_code == 409

    def test_delete_group(self, api_client: TestClient) -> None:
        created = api_client.post("/api/signal-config-groups", json=_group_payload()).json()

        assert api_client.delete(f"/api/signal-config-groups/{created['id']}").status_code == 204
        assert api_client.get(f"/api/signal-config-groups/{created['id']}").status_code == 404

    def test_delete_nonexistent_group_returns_404(self, api_client: TestClient) -> None:
        response = api_client.delete(f"/api/signal-config-groups/{uuid4()}")
        assert response.status_code == 404


class TestSignalDeletionCleansGroupMembership:
    def test_deleting_signal_removes_it_from_one_group(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig_id = _create_signal(session_factory)
        group = api_client.post(
            "/api/signal-config-groups", json=_group_payload(signal_ids=[sig_id])
        ).json()

        assert api_client.delete(f"/api/signal-definitions/{sig_id}").status_code == 204

        updated = api_client.get(f"/api/signal-config-groups/{group['id']}").json()
        assert updated["signal_ids"] == []

    def test_deleting_signal_removes_it_from_multiple_groups(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig_a = _create_signal(session_factory, "Signal A")
        sig_b = _create_signal(session_factory, "Signal B")
        group1 = api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(name="Group 1", signal_ids=[sig_a, sig_b]),
        ).json()
        group2 = api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(name="Group 2", signal_ids=[sig_a]),
        ).json()

        assert api_client.delete(f"/api/signal-definitions/{sig_a}").status_code == 204

        assert api_client.get(f"/api/signal-config-groups/{group1['id']}").json()["signal_ids"] == [
            sig_b
        ]
        assert (
            api_client.get(f"/api/signal-config-groups/{group2['id']}").json()["signal_ids"] == []
        )

    def test_deleting_signal_preserves_order_of_remaining_ids(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig_a = _create_signal(session_factory, "Signal A")
        sig_b = _create_signal(session_factory, "Signal B")
        sig_c = _create_signal(session_factory, "Signal C")
        group = api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(signal_ids=[sig_a, sig_b, sig_c]),
        ).json()

        assert api_client.delete(f"/api/signal-definitions/{sig_b}").status_code == 204

        updated = api_client.get(f"/api/signal-config-groups/{group['id']}").json()
        assert updated["signal_ids"] == [sig_a, sig_c]

    def test_deleting_signal_leaves_unrelated_group_untouched(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig_a = _create_signal(session_factory, "Signal A")
        sig_b = _create_signal(session_factory, "Signal B")
        api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(name="Group with A", signal_ids=[sig_a]),
        )
        unrelated = api_client.post(
            "/api/signal-config-groups",
            json=_group_payload(name="Group with B", signal_ids=[sig_b]),
        ).json()

        assert api_client.delete(f"/api/signal-definitions/{sig_a}").status_code == 204

        after = api_client.get(f"/api/signal-config-groups/{unrelated['id']}").json()
        assert after["signal_ids"] == [sig_b]
        assert after["updated_at"] == unrelated["updated_at"]

    def test_deleting_signal_not_in_any_group_succeeds(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig_id = _create_signal(session_factory)
        assert api_client.delete(f"/api/signal-definitions/{sig_id}").status_code == 204

    def test_deleted_signal_is_gone(
        self, api_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        sig_id = _create_signal(session_factory)
        api_client.post("/api/signal-config-groups", json=_group_payload(signal_ids=[sig_id]))
        assert api_client.delete(f"/api/signal-definitions/{sig_id}").status_code == 204
        assert api_client.get(f"/api/signal-definitions/{sig_id}").status_code == 404


def test_deleting_group_referenced_by_team_is_rejected(api_client: TestClient) -> None:
    group = api_client.post("/api/signal-config-groups", json=_group_payload()).json()
    api_client.post(
        "/api/teams",
        json={"name": "Platform", "signal_config_group_ids": [group["id"]]},
    )

    response = api_client.delete(f"/api/signal-config-groups/{group['id']}")

    assert response.status_code == 409
    assert response.json()["detail"] == "signal config group is referenced by a team"


def test_unreferenced_group_can_be_deleted(api_client: TestClient) -> None:
    group = api_client.post("/api/signal-config-groups", json=_group_payload()).json()

    assert api_client.delete(f"/api/signal-config-groups/{group['id']}").status_code == 204


def test_alembic_revision_applies_on_in_memory_sqlite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "migration-groups.db"
    monkeypatch.setenv(DATABASE_PATH_ENV, str(database_path))
    config = Config(REPO_ROOT / "alembic.ini")

    command.upgrade(config, "head")
    table_names = set(inspect(create_db_engine(database_path)).get_table_names())
    assert "signal_config_group" in table_names

    command.downgrade(config, "2a8c3d7e9f1b-1")
    table_names_after = set(inspect(create_db_engine(database_path)).get_table_names())
    assert "signal_config_group" not in table_names_after
