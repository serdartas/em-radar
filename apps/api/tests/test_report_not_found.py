"""Tests for report 404 on unknown ID (AUDIT-27)."""

import uuid

from fastapi.testclient import TestClient


def test_get_report_returns_404_for_unknown_id(api_client: TestClient) -> None:
    unknown_id = uuid.uuid4()
    response = api_client.get(f"/api/reports/{unknown_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "report not found"
