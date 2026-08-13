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
_SIGNAL_ID = str(uuid4())
_SOURCE_LINK = "https://demo.invalid/browse/PLAT-9"


def _section_body(markdown: str, section_title: str) -> str:
    """Return the lines under a ``## <section_title>`` heading, up to the next ``## `` heading."""
    lines = markdown.splitlines()
    start = lines.index(f"## {section_title}") + 1
    end = start
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    return "\n".join(lines[start:end])


def _persist_report(session_factory: sessionmaker[Session]) -> UUID:
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
                        "id": _SIGNAL_ID,
                        "name": "Blocked without update",
                        "entity_type": "workitem",
                        "category": "flow",
                        "enabled": True,
                        "origin": "user_created",
                        "template_key": None,
                        "version": 1,
                    }
                ],
                "skipped_signals": [
                    {
                        "id": str(uuid4()),
                        "name": "MR without linked work item",
                        "reason": "code source not attached",
                    }
                ],
                "partial_data_notes": [
                    {"source": "board", "reason": "board data unavailable: ConnectorAuthError"}
                ],
            },
            status=ReportStatus.SUCCEEDED,
            started_at=_NOW,
            finished_at=_NOW,
            findings_count_by_severity={
                Severity.INFO: 0,
                Severity.WARNING: 0,
                Severity.CRITICAL: 1,
            },
        )
        session.add(report)
        session.commit()
        session.refresh(report)

        session.add(
            SignalFindingTable(
                report_id=report.id,
                signal_id=_SIGNAL_ID,
                signal_name="Blocked without update",
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                entity_type=EntityType.WORKITEM,
                entity_id=uuid4(),
                title="PLAT-9 blocked for 6 days",
                reason="Blocked and untouched.",
                recommendation="Escalate the blocker.",
                evidence={"days_blocked": 6},
                source_link=_SOURCE_LINK,
                created_at=_NOW,
            )
        )
        session.commit()
        return report.id


def test_export_markdown_returns_markdown_body(
    api_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    report_id = _persist_report(session_factory)

    response = api_client.get(f"/api/reports/{report_id}/export.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert f'filename="report-{report_id}.md"' in response.headers["content-disposition"]

    body = response.text
    # Report title + metadata block.
    assert body.startswith("# EM Radar Report")
    assert f"- **Report:** {report_id}" in body
    assert "- **Team:** Platform Team" in body
    assert "- **Generated:** 2026-06-01T10:00:00+00:00" in body
    # Grouped section headings.
    assert "## Summary" in body
    assert "## Delivery Flow" in body
    assert "## Detailed Findings" in body
    # The finding and its source link.
    assert "### PLAT-9 blocked for 6 days" in body
    assert f"- **Source:** [PLAT-9 blocked for 6 days](<{_SOURCE_LINK}>)" in body
    # The reconstructed category="flow" must route the finding into Delivery Flow:
    # assert its heading appears within that section (before the next "## " heading).
    delivery_section = _section_body(body, "Delivery Flow")
    assert "### PLAT-9 blocked for 6 days" in delivery_section
    # Skip / partial-data notes reconstructed from the snapshot.
    assert "## Skipped Signals" in body
    assert "- **MR without linked work item:** code source not attached" in body
    assert "## Partial Data" in body
    assert "- **board:** board data unavailable: ConnectorAuthError" in body


def test_export_markdown_unknown_report_returns_404(api_client: TestClient) -> None:
    response = api_client.get(f"/api/reports/{uuid4()}/export.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "report not found"
