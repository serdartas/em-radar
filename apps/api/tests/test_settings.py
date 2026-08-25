# SPDX-License-Identifier: Apache-2.0

from fastapi.testclient import TestClient


def test_default_settings_telemetry_off(api_client: TestClient) -> None:
    resp = api_client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["telemetry_enabled"] is False


def test_patch_persists_telemetry_on(api_client: TestClient) -> None:
    patch = api_client.patch("/api/settings", json={"telemetry_enabled": True})
    assert patch.status_code == 200
    assert patch.json()["telemetry_enabled"] is True

    get = api_client.get("/api/settings")
    assert get.status_code == 200
    assert get.json()["telemetry_enabled"] is True


def test_patch_can_turn_telemetry_off_again(api_client: TestClient) -> None:
    api_client.patch("/api/settings", json={"telemetry_enabled": True})
    api_client.patch("/api/settings", json={"telemetry_enabled": False})

    get = api_client.get("/api/settings")
    assert get.json()["telemetry_enabled"] is False


def test_default_date_format_is_ddmmyyyy(api_client: TestClient) -> None:
    resp = api_client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["date_format"] == "dd/mm/yyyy"


def test_patch_date_format_mmddyyyy(api_client: TestClient) -> None:
    patch = api_client.patch("/api/settings", json={"date_format": "mm/dd/yyyy"})
    assert patch.status_code == 200
    assert patch.json()["date_format"] == "mm/dd/yyyy"

    get = api_client.get("/api/settings")
    assert get.status_code == 200
    assert get.json()["date_format"] == "mm/dd/yyyy"


def test_patch_date_format_iso(api_client: TestClient) -> None:
    patch = api_client.patch("/api/settings", json={"date_format": "yyyy-mm-dd"})
    assert patch.status_code == 200
    assert patch.json()["date_format"] == "yyyy-mm-dd"


def test_patch_date_format_invalid_rejected(api_client: TestClient) -> None:
    patch = api_client.patch("/api/settings", json={"date_format": "invalid-format"})
    assert patch.status_code == 422


def test_patch_date_format_does_not_reset_telemetry(api_client: TestClient) -> None:
    api_client.patch("/api/settings", json={"telemetry_enabled": True})
    api_client.patch("/api/settings", json={"date_format": "mm/dd/yyyy"})

    get = api_client.get("/api/settings")
    data = get.json()
    assert data["telemetry_enabled"] is True
    assert data["date_format"] == "mm/dd/yyyy"
