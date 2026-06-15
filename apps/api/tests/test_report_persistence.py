from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from em_radar_api.repositories.reports import get_findings, get_report
from em_radar_api.tables import ReportTable, SignalFindingTable, WorkItemTable


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


def test_report_run_follows_status_lifecycle(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from em_radar_api.routers import reports

    statuses: list[str] = []
    original_create_report = reports.create_report
    original_save_report = reports.save_report

    def capture_create(session: Session, report: ReportTable) -> ReportTable:
        statuses.append(str(report.status))
        return original_create_report(session, report)

    def capture_save(session: Session, report: ReportTable) -> ReportTable:
        statuses.append(str(report.status))
        return original_save_report(session, report)

    monkeypatch.setattr(reports, "create_report", capture_create)
    monkeypatch.setattr(reports, "save_report", capture_save)

    assert api_client.post("/api/reports/run", json={"connector": "demo"}).status_code == 200
    assert statuses == ["pending", "running", "succeeded"]


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


def test_findings_reference_persisted_entities(api_harness: SimpleNamespace) -> None:
    report_id = api_harness.client.post("/api/reports/run", json={"connector": "demo"}).json()["id"]

    with api_harness.session_factory() as session:
        findings = session.exec(
            select(SignalFindingTable).where(SignalFindingTable.report_id == UUID(report_id))
        ).all()
        workitem_ids = set(session.exec(select(WorkItemTable.id)).all())

    assert findings
    assert {finding.entity_id for finding in findings} <= workitem_ids
    assert len({finding.uniqueness_key for finding in findings}) == len(findings)


def test_insert_failure_marks_report_failed(
    api_harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from em_radar_api.routers import reports

    def add_duplicate_findings(session: Session, findings: list[SignalFindingTable]) -> None:
        first = findings[0]
        duplicate_data = first.model_dump()
        duplicate_data["id"] = uuid4()
        duplicate = SignalFindingTable(**duplicate_data)
        session.add_all([first, duplicate])
        session.commit()

    monkeypatch.setattr(reports, "add_findings", add_duplicate_findings)

    with pytest.raises(IntegrityError):
        api_harness.client.post("/api/reports/run", json={"connector": "demo"})

    with api_harness.session_factory() as session:
        report = session.exec(select(ReportTable)).one()

    assert report.status == "failed"
    assert report.finished_at is not None
    assert report.error is not None


def test_get_unknown_report_returns_404(api_client: TestClient) -> None:
    assert api_client.get(f"/api/reports/{uuid4()}").status_code == 404
