from datetime import timedelta

from em_radar_connector_demo import FIXTURE_NOW
from fastapi.testclient import TestClient

from em_radar_api.main import app


def test_run_demo_report_returns_deterministic_stale_findings() -> None:
    client = TestClient(app)

    first = client.post("/api/reports/run", json={"connector": "demo"})
    second = client.post("/api/reports/run", json={"connector": "demo"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(first.json()["findings"]) > 0
    assert {finding["signal_id"] for finding in first.json()["findings"]} == {
        "stale-in-progress-work-item"
    }


def test_run_demo_report_accepts_date_range_window() -> None:
    response = TestClient(app).post(
        "/api/reports/run",
        json={
            "connector": "demo",
            "window": {
                "window_type": "date_range",
                "start": (FIXTURE_NOW - timedelta(days=90)).isoformat(),
                "end": FIXTURE_NOW.isoformat(),
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["findings"]


def test_run_report_rejects_non_demo_connector_and_invalid_window() -> None:
    client = TestClient(app)

    assert client.post("/api/reports/run", json={"connector": "jira"}).status_code == 422
    assert (
        client.post(
            "/api/reports/run",
            json={"connector": "demo", "window": {"window_type": "sprint"}},
        ).status_code
        == 422
    )
