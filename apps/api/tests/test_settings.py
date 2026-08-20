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
