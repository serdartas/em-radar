from collections.abc import Sequence
from uuid import UUID

from sqlmodel import Session, desc, select

from em_radar_api.tables import ReportTable, SignalFindingTable


def create_report(session: Session, report: ReportTable) -> ReportTable:
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def save_report(session: Session, report: ReportTable) -> ReportTable:
    """Persist a status-lifecycle update (running → succeeded|failed) for an existing report."""
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def add_findings(session: Session, findings: Sequence[SignalFindingTable]) -> None:
    """Insert findings, relying on the ``(report_id, signal_id, entity_type, entity_id)``
    table constraint to reject duplicates."""
    session.add_all(findings)
    session.commit()


def list_reports(session: Session) -> list[ReportTable]:
    return list(session.exec(select(ReportTable).order_by(desc(ReportTable.started_at))))


def get_report(session: Session, report_id: UUID) -> ReportTable | None:
    return session.get(ReportTable, report_id)


def get_findings(session: Session, report_id: UUID) -> list[SignalFindingTable]:
    return list(
        session.exec(select(SignalFindingTable).where(SignalFindingTable.report_id == report_id))
    )
