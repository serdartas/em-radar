from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from em_radar_core.models import (
    Confidence,
    EntityType,
    ReportStatus,
    Severity,
    WindowType,
)

from em_radar_api.tables import (
    EvaluationWindowTable,
    ReportTable,
    SignalFindingTable,
    TeamProfileTable,
)

_NOW = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
_FLOW_SIGNAL_ID = str(uuid4())
_HYGIENE_SIGNAL_ID = str(uuid4())
_SKIPPED_SIGNAL_ID = str(uuid4())

_SECTION_ORDER = [
    ("summary", "Summary"),
    ("top_risks", "Top Risks"),
    ("planning_hygiene", "Planning Hygiene"),
    ("delivery_flow", "Delivery Flow"),
    ("sprint_health", "Sprint Health"),
    ("merge_request_flow", "Merge Request Flow"),
    ("source_linking", "Source Linking"),
    ("detailed_findings", "Detailed Findings"),
    ("suggested_actions", "Suggested Actions"),
]


def _persist_report(session_factory: sessionmaker[Session]) -> tuple[UUID, str, str]:
    with session_factory() as session:
        team = TeamProfileTable(name="Platform Team", created_at=_NOW, updated_at=_NOW)
        session.add(team)
        session.commit()
        session.refresh(team)

        window = EvaluationWindowTable(
            window_type=WindowType.DATE_RANGE,
            start=datetime(2026, 5, 18, tzinfo=UTC),
            end=_NOW,
            team_profile_id=team.id,
        )
        session.add(window)
        session.commit()
        session.refresh(window)

        report = ReportTable(
            evaluation_window_id=window.id,
            signal_pack_snapshot={
                "schema_id": "emradar.dev/v1",
                "signal_config_group_ids": [],
                "signal_definitions": [
                    {
                        "id": _FLOW_SIGNAL_ID,
                        "name": "Blocked without update",
                        "entity_type": "workitem",
                        "category": "flow",
                        "enabled": True,
                        "origin": "user_created",
                        "template_key": None,
                        "version": 1,
                    },
                    {
                        "id": _HYGIENE_SIGNAL_ID,
                        "name": "Missing estimate",
                        "entity_type": "workitem",
                        "category": "hygiene",
                        "enabled": True,
                        "origin": "user_created",
                        "template_key": None,
                        "version": 1,
                    },
                ],
                "skipped_signals": [
                    {
                        "id": _SKIPPED_SIGNAL_ID,
                        "name": "MR without linked work item",
                        "reason": "code source not attached",
                    }
                ],
                "partial_data_notes": [],
            },
            status=ReportStatus.SUCCEEDED,
            started_at=_NOW,
            finished_at=_NOW,
            error=None,
            findings_count_by_severity={
                Severity.INFO: 0,
                Severity.WARNING: 1,
                Severity.CRITICAL: 1,
            },
        )
        session.add(report)
        session.commit()
        session.refresh(report)

        critical = SignalFindingTable(
            report_id=report.id,
            signal_id=_FLOW_SIGNAL_ID,
            signal_name="Blocked without update",
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
            entity_type=EntityType.WORKITEM,
            entity_id=uuid4(),
            title="PLAT-9 blocked for 6 days",
            reason="Blocked and untouched.",
            recommendation="Escalate the blocker.",
            evidence={"days_blocked": 6},
            source_link="https://demo.invalid/browse/PLAT-9",
            created_at=_NOW,
        )
        warning = SignalFindingTable(
            report_id=report.id,
            signal_id=_HYGIENE_SIGNAL_ID,
            signal_name="Missing estimate",
            severity=Severity.WARNING,
            confidence=Confidence.MEDIUM,
            entity_type=EntityType.WORKITEM,
            entity_id=uuid4(),
            title="PLAT-4 has no estimate",
            reason="No estimate set.",
            recommendation="Add an estimate.",
            evidence={"estimate": None},
            source_link="https://demo.invalid/browse/PLAT-4",
            created_at=_NOW,
        )
        session.add(critical)
        session.add(warning)
        session.commit()
        session.refresh(critical)
        session.refresh(warning)
        return report.id, str(critical.id), str(warning.id)


def test_detail_response_exposes_ordered_sections(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    report_id, critical_id, warning_id = _persist_report(session_factory)

    response = api_client.get(f"/api/reports/{report_id}")
    assert response.status_code == 200
    body = response.json()

    assert [
        (section["section"], section["title"]) for section in body["sections"]
    ] == _SECTION_ORDER

    sections = {section["section"]: section for section in body["sections"]}
    assert sections["delivery_flow"]["finding_ids"] == [critical_id]
    assert sections["planning_hygiene"]["finding_ids"] == [warning_id]
    # Detailed Findings and Top Risks are severity-ordered: critical before warning.
    assert sections["detailed_findings"]["finding_ids"] == [critical_id, warning_id]
    assert sections["top_risks"]["finding_ids"] == [critical_id, warning_id]
    assert sections["summary"]["finding_ids"] == []


def test_detail_response_exposes_summary_and_finding_ids(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    report_id, critical_id, warning_id = _persist_report(session_factory)

    body = api_client.get(f"/api/reports/{report_id}").json()

    assert body["summary"]["total"] == 2
    assert body["summary"]["counts_by_severity"] == {"info": 0, "warning": 1, "critical": 1}

    finding_ids = {finding["id"] for finding in body["findings"]}
    assert finding_ids == {critical_id, warning_id}


def test_detail_response_surfaces_skip_notes(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    report_id, _, _ = _persist_report(session_factory)

    body = api_client.get(f"/api/reports/{report_id}").json()

    assert body["skip_notes"] == [
        {"signal_id": "MR without linked work item", "reason": "code source not attached"}
    ]
