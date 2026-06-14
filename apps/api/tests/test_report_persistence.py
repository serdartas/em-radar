from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlmodel import select

from em_radar_api.repositories.reports import get_findings, get_report


def test_demo_run_persists_succeeded_report_with_severity_counts(api_client: TestClient) -> None:
    run = api_client.post("/api/reports/run", json={"connector": "demo"})

    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "succeeded"
    assert body["started_at"] is not None
    assert body["finished_at"] is not None
    assert body["error"] is None

    counts = body["findings_count_by_severity"]
    assert set(counts) == {"info", "warning", "critical"}
    assert sum(counts.values()) == len(body["findings"])
    assert counts["warning"] == len(body["findings"])
    assert body["signal_pack_snapshot"]["schema_id"] == "emradar.dev/v1"


def test_get_report_returns_persisted_detail_and_list(api_client: TestClient) -> None:
    report_id = api_client.post("/api/reports/run", json={"connector": "demo"}).json()["id"]

    detail = api_client.get(f"/api/reports/{report_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == report_id
    assert len(detail.json()["findings"]) > 0

    listed = api_client.get("/api/reports")
    assert listed.status_code == 200
    assert report_id in {report["id"] for report in listed.json()}


def test_report_survives_a_fresh_db_session(api_harness: SimpleNamespace) -> None:
    report_id = api_harness.client.post("/api/reports/run", json={"connector": "demo"}).json()["id"]

    with api_harness.session_factory() as session:
        report = get_report(session, UUID(report_id))
        findings = get_findings(session, UUID(report_id))

    assert report is not None
    assert str(report.id) == report_id
    assert report.status == "succeeded"
    assert len(findings) > 0
    assert all(str(finding.report_id) == report_id for finding in findings)


def test_findings_uniqueness_invariant_is_enforced(api_harness: SimpleNamespace) -> None:
    from em_radar_api.tables import SignalFindingTable

    report_id = api_harness.client.post("/api/reports/run", json={"connector": "demo"}).json()["id"]

    with api_harness.session_factory() as session:
        findings = session.exec(
            select(SignalFindingTable).where(SignalFindingTable.report_id == UUID(report_id))
        ).all()
        keys = {finding.uniqueness_key for finding in findings}

    assert len(keys) == len(findings)


def test_get_unknown_report_returns_404(api_client: TestClient) -> None:
    assert api_client.get(f"/api/reports/{uuid4()}").status_code == 404
