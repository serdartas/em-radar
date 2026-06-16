from datetime import timedelta

from em_radar_connector_demo import FIXTURE_NOW
from fastapi.testclient import TestClient


def test_run_demo_report_returns_deterministic_stale_findings(api_client: TestClient) -> None:
    first = api_client.post("/api/reports/run", json={"connector": "demo"})
    second = api_client.post("/api/reports/run", json={"connector": "demo"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["findings"] == second.json()["findings"]
    assert len(first.json()["findings"]) > 0
    assert {finding["signal_id"] for finding in first.json()["findings"]} == {
        "stale-in-progress-work-item"
    }


def test_run_demo_report_accepts_date_range_window(api_client: TestClient) -> None:
    response = api_client.post(
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


def test_run_demo_report_uses_persisted_signal_configs(api_client: TestClient) -> None:
    patch_response = api_client.patch(
        "/api/signal-configs/stale-in-progress-work-item",
        json={"enabled": False},
    )
    response = api_client.post("/api/reports/run", json={"connector": "demo"})

    assert patch_response.status_code == 200
    assert response.status_code == 200
    assert {finding["signal_id"] for finding in response.json()["findings"]} != {
        "stale-in-progress-work-item"
    }
    assert all(
        finding["signal_id"] != "stale-in-progress-work-item"
        for finding in response.json()["findings"]
    )


def test_run_report_rejects_missing_jira_scope_and_invalid_window(api_client: TestClient) -> None:
    assert api_client.post("/api/reports/run", json={"connector": "jira"}).status_code == 422
    assert (
        api_client.post(
            "/api/reports/run",
            json={"connector": "demo", "window": {"window_type": "sprint"}},
        ).status_code
        == 422
    )
