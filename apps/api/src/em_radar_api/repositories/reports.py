# SPDX-License-Identifier: Apache-2.0

from collections.abc import Sequence
from uuid import UUID

from sqlmodel import Session, delete, desc, select

from em_radar_api.tables import EvaluationWindowTable, ReportJobTable, ReportTable, SignalFindingTable


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


def delete_reports_for_team(session: Session, team_id: UUID) -> None:
    """Delete all reports, findings, evaluation windows, and job rows for a team."""
    # Delete job rows first: a report that failed before persisting an evaluation window
    # (no source, unresolvable sprint) leaves a ReportJobTable row but no window, so this
    # must run even when the team has no windows.
    session.exec(delete(ReportJobTable).where(ReportJobTable.team_profile_id == team_id))

    window_ids: list[UUID] = list(
        session.exec(
            select(EvaluationWindowTable.id).where(EvaluationWindowTable.team_profile_id == team_id)
        )
    )
    if not window_ids:
        session.commit()
        return

    report_ids: list[UUID] = list(
        session.exec(select(ReportTable.id).where(ReportTable.evaluation_window_id.in_(window_ids)))
    )
    if report_ids:
        session.exec(delete(SignalFindingTable).where(SignalFindingTable.report_id.in_(report_ids)))
    session.exec(delete(ReportTable).where(ReportTable.evaluation_window_id.in_(window_ids)))
    session.exec(
        delete(EvaluationWindowTable).where(EvaluationWindowTable.team_profile_id == team_id)
    )
    session.commit()


def delete_all_reports(session: Session) -> None:
    """Delete every report, finding, evaluation window, and job row in the database."""
    session.exec(delete(SignalFindingTable))
    session.exec(delete(ReportTable))
    session.exec(delete(EvaluationWindowTable))
    session.exec(delete(ReportJobTable))
    session.commit()
