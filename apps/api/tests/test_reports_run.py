from datetime import timedelta

from em_radar_connector_demo import FIXTURE_NOW
from em_radar_core.models import Severity
from em_radar_api.signal_configs import SignalConfigUpsert
from em_radar_api.repositories.signal_configs import upsert_signal_config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session


def test_run_demo_report_returns_deterministic_signal_findings(api_client: TestClient) -> None:
    first = api_client.post("/api/reports/run", json={"connector": "demo"})
    second = api_client.post("/api/reports/run", json={"connector": "demo"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["findings"] == second.json()["findings"]
    assert len(first.json()["findings"]) > 0
    signal_ids = {finding["signal_id"] for finding in first.json()["findings"]}
    assert "stale-in-progress-work-item" in signal_ids
    assert "story-without-acceptance-criteria" in signal_ids


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


def test_run_demo_report_uses_severity_overrides_and_effective_snapshot(
    api_client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        upsert_signal_config(
            session,
            SignalConfigUpsert(
                signal_id="story-without-acceptance-criteria",
                severity_override=Severity.CRITICAL,
                params={},
            ),
        )
        upsert_signal_config(
            session,
            SignalConfigUpsert(
                signal_id="stale-in-progress-work-item",
                enabled=True,
                params={"days_threshold": 11},
            ),
        )

    response = api_client.post("/api/reports/run", json={"connector": "demo"})

    assert response.status_code == 200
    body = response.json()
    acceptance_findings = [
        finding
        for finding in body["findings"]
        if finding["signal_id"] == "story-without-acceptance-criteria"
    ]
    assert acceptance_findings
    assert {finding["severity"] for finding in acceptance_findings} == {"critical"}

    snapshot = {signal["id"]: signal for signal in body["signal_pack_snapshot"]["signals"]}
    assert snapshot["story-without-acceptance-criteria"]["severity"] == "critical"
    assert snapshot["stale-in-progress-work-item"]["enabled"] is True
    assert snapshot["stale-in-progress-work-item"]["params"]["days_threshold"] == 11


def test_run_report_rejects_missing_jira_scope_and_invalid_window(api_client: TestClient) -> None:
    assert api_client.post("/api/reports/run", json={"connector": "jira"}).status_code == 422
    assert (
        api_client.post(
            "/api/reports/run",
            json={"connector": "demo", "window": {"window_type": "sprint"}},
        ).status_code
        == 422
    )
