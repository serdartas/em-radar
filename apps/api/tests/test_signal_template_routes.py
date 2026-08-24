"""Tests for signal-template routes (AUDIT-24)."""

from fastapi.testclient import TestClient


def test_list_signal_templates_returns_list_with_required_shape(api_client: TestClient) -> None:
    response = api_client.get("/api/signal-templates")

    assert response.status_code == 200
    templates = response.json()
    assert isinstance(templates, list)
    assert len(templates) > 0
    for template in templates:
        assert "key" in template
        assert "name" in template
        assert "description" in template
        assert "required_connector_type" in template
        assert "entity_type" in template
        assert "required_scope_capabilities" in template
        assert "expression" in template
        assert "report_settings" in template


def test_restore_known_signal_template_returns_200(api_client: TestClient) -> None:
    templates = api_client.get("/api/signal-templates").json()
    key = templates[0]["key"]

    response = api_client.post(f"/api/signal-templates/{key}/restore")

    assert response.status_code == 200
    body = response.json()
    assert body["key"] == key
    assert "name" in body


def test_restore_unknown_signal_template_returns_404(api_client: TestClient) -> None:
    response = api_client.post("/api/signal-templates/no-such-template-xyz/restore")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
