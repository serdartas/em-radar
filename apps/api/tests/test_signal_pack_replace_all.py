"""Tests asserting replace_all mode is rejected with 422 on both import endpoints (AUDIT-26)."""

from fastapi.testclient import TestClient

_MINIMAL_YAML = "apiVersion: emradar.dev/v1\nkind: SignalPack\n"


def test_preview_import_rejects_replace_all_mode(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/signal-pack/import",
        json={"raw_yaml": _MINIMAL_YAML, "mode": "replace_all"},
    )

    assert response.status_code == 422
    assert "replace_all" in response.json()["detail"]


def test_apply_import_rejects_replace_all_mode(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/signal-pack/import/apply",
        json={"raw_yaml": _MINIMAL_YAML, "mode": "replace_all"},
    )

    assert response.status_code == 422
    assert "replace_all" in response.json()["detail"]
