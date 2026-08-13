from collections.abc import Sequence

from em_radar_core.models import SignalFinding, WindowType
from em_radar_reports import (
    PartialDataNote,
    ReportMetadata,
    SectionedReport,
    SignalMeta,
    SkipNote,
    build_sections,
    render_markdown,
)

from em_radar_api.tables import EvaluationWindowTable, ReportTable, TeamProfileTable


def build_sectioned_report(
    report: ReportTable,
    findings: Sequence[SignalFinding],
) -> SectionedReport:
    """Reconstruct the sectioned model (M6-01) from a persisted report.

    Section-assignment metadata (category, template_key) and the skip / partial-data
    notes are read back from the report's ``signal_pack_snapshot`` so the sections
    reflect the signal configuration captured at run time, not the signals' current
    state. Shared by the Markdown export and the detail API response.
    """
    snapshot = report.signal_pack_snapshot
    return build_sections(
        findings,
        _signal_meta_from_snapshot(snapshot),
        skip_notes=_skip_notes_from_snapshot(snapshot),
        partial_data_notes=_partial_data_notes_from_snapshot(snapshot),
    )


def build_report_markdown(
    report: ReportTable,
    findings: Sequence[SignalFinding],
    window: EvaluationWindowTable | None,
    team: TeamProfileTable | None,
    sprint_label: str | None = None,
) -> str:
    """Reconstruct the sectioned Markdown export (M6-04) for a persisted report.

    Section-assignment metadata (category, template_key) and the skip / partial-data
    notes are read back from the report's ``signal_pack_snapshot`` so the export
    reflects the signal configuration captured at run time, not the signals' current
    state. ``generated_at`` is the report's stored ``started_at`` — the
    ``EvaluationContext.now`` the run evaluated against — never a wall-clock read, so
    identical reports export byte-identically.
    """
    sectioned = build_sectioned_report(report, findings)
    metadata = ReportMetadata(
        report_id=report.id,
        generated_at=report.started_at,
        status=report.status,
        error=report.error,
        window_type=window.window_type if window is not None else WindowType.DATE_RANGE,
        team_name=team.name if team is not None else None,
        team_id=team.id if team is not None else None,
        window_start=window.start if window is not None else None,
        window_end=window.end if window is not None else None,
        sprint_id=window.sprint_id if window is not None else None,
        sprint_label=sprint_label,
    )
    return render_markdown(sectioned, metadata)


def _signal_meta_from_snapshot(snapshot: object) -> dict[str, SignalMeta]:
    meta: dict[str, SignalMeta] = {}
    definitions = snapshot.get("signal_definitions") if isinstance(snapshot, dict) else None
    if not isinstance(definitions, list):
        return meta
    for entry in definitions:
        if not isinstance(entry, dict):
            continue
        signal_id = entry.get("id")
        if not isinstance(signal_id, str):
            continue
        category = entry.get("category")
        template_key = entry.get("template_key")
        meta[signal_id] = SignalMeta(
            category=category if isinstance(category, str) else "",
            template_key=template_key if isinstance(template_key, str) else None,
        )
    return meta


def _skip_notes_from_snapshot(snapshot: object) -> list[SkipNote]:
    entries = snapshot.get("skipped_signals") if isinstance(snapshot, dict) else None
    if not isinstance(entries, list):
        return []
    notes: list[SkipNote] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        reason = entry.get("reason")
        # Prefer the human-readable signal name over its id for a readable export.
        label = entry.get("name") or entry.get("id")
        if isinstance(label, str) and isinstance(reason, str):
            notes.append(SkipNote(signal_id=label, reason=reason))
    return notes


def _partial_data_notes_from_snapshot(snapshot: object) -> list[PartialDataNote]:
    entries = snapshot.get("partial_data_notes") if isinstance(snapshot, dict) else None
    if not isinstance(entries, list):
        return []
    notes: list[PartialDataNote] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        reason = entry.get("reason")
        if isinstance(source, str) and isinstance(reason, str):
            notes.append(PartialDataNote(source=source, reason=reason))
    return notes
