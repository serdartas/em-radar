import html
import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import UUID

from em_radar_core.models import ReportStatus, Severity, SignalFinding, WindowType
from pydantic import BaseModel, ConfigDict, JsonValue

from em_radar_reports.sectioning import SECTION_ORDER, Section, SectionedReport

REPORT_TITLE: str = "EM Radar Report"

# Fixed, most-urgent-first order for rendering the summary counts. Independent of
# the Severity enum's declaration order so the summary layout stays stable even if
# the enum is ever reordered.
_SUMMARY_SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.WARNING,
    Severity.INFO,
)

_SEVERITY_LABEL: dict[Severity, str] = {
    Severity.CRITICAL: "Critical",
    Severity.WARNING: "Warning",
    Severity.INFO: "Info",
}

_STATUS_LABEL: dict[ReportStatus, str] = {
    ReportStatus.PENDING: "Pending",
    ReportStatus.RUNNING: "Running",
    ReportStatus.SUCCEEDED: "Succeeded",
    ReportStatus.FAILED: "Failed",
}

_FAILURE_NOTICE: str = "> **This report did not complete successfully.**"

_NO_FINDINGS: str = "_No findings._"

_WHITESPACE = re.compile(r"\s+")

# CommonMark and GFM ASCII punctuation that must be backslash-escaped so source
# text is rendered literally (tilde covers GFM strikethrough). Backslash is
# included so it is escaped too; str.translate runs in a single pass, so escaped
# backslashes are never re-escaped. Quotes are intentionally excluded so
# JSON-serialized evidence keeps its double quotes.
_MD_ESCAPE = str.maketrans({char: f"\\{char}" for char in "\\`*_[](){}#+!|~"})


class ReportMetadata(BaseModel):
    """Provenance the caller attaches to an export so runs are distinguishable.

    The M6-05 API builds this from the persisted `Report`, `EvaluationWindow`, and
    `TeamProfile`. `generated_at` is an input (the report's stored start/finish
    time) never a wall-clock read, so identical inputs render byte-identically.
    """

    model_config = ConfigDict(frozen=True)

    report_id: UUID
    generated_at: datetime
    status: ReportStatus
    window_type: WindowType
    error: str | None = None
    team_name: str | None = None
    team_id: UUID | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    sprint_id: UUID | None = None
    sprint_label: str | None = None


def render_markdown(report: SectionedReport, metadata: ReportMetadata) -> str:
    """Render a sectioned report to portable, deterministic Markdown.

    The same `(SectionedReport, ReportMetadata)` pair always renders byte-identically:
    findings keep the severity order M6-01 already applied, summary counts render in a
    fixed order, evidence keys are sorted, skip/partial-data notes are sorted, and the
    generation timestamp is an input formatted as UTC ISO 8601. Finding text is
    sanitized (whitespace collapsed, link syntax escaped, URLs angle-bracket wrapped)
    so titles or reasons carrying Markdown metacharacters or newlines cannot break a
    link or split a list item. Only stdlib and `em_radar_core` are used, keeping the
    reports package source-agnostic.
    """
    lines: list[str] = [f"# {REPORT_TITLE}", ""]
    notice = _render_failure_notice(metadata)
    if notice:
        lines.extend(notice)
        lines.append("")
    lines.extend(_render_metadata(metadata))
    lines.append("")

    for section in SECTION_ORDER:
        lines.append(f"## {section.title}")
        lines.append("")
        if section is Section.SUMMARY:
            lines.extend(_render_summary(report))
        else:
            lines.extend(_render_findings(report.get_section(section).findings))
        lines.append("")

    lines.extend(_render_notes(report))

    return "\n".join(lines).rstrip("\n") + "\n"


def _render_failure_notice(metadata: ReportMetadata) -> list[str]:
    """Unmistakable notice for a non-succeeded run, so a failed export is never mistaken
    for a valid zero-finding report. Empty for a succeeded report."""
    if metadata.status is ReportStatus.SUCCEEDED:
        return []
    lines = [
        _FAILURE_NOTICE,
        ">",
        f"> **Status:** {_STATUS_LABEL[metadata.status]}",
    ]
    if metadata.error:
        lines.append(">")
        lines.append(f"> **Error:** {_inline(metadata.error)}")
    return lines


def _render_metadata(metadata: ReportMetadata) -> list[str]:
    lines = [f"- **Report:** {metadata.report_id}"]
    team = _format_team(metadata)
    if team:
        lines.append(f"- **Team:** {team}")
    lines.append(f"- **Window:** {_format_window(metadata)}")
    lines.append(f"- **Generated:** {_format_datetime(metadata.generated_at)}")
    lines.append(f"- **Status:** {_STATUS_LABEL[metadata.status]}")
    return lines


def _format_team(metadata: ReportMetadata) -> str:
    if metadata.team_name and metadata.team_id:
        return f"{_inline(metadata.team_name)} ({metadata.team_id})"
    if metadata.team_name:
        return _inline(metadata.team_name)
    if metadata.team_id:
        return str(metadata.team_id)
    return ""


def _format_window(metadata: ReportMetadata) -> str:
    if metadata.window_type is WindowType.SPRINT:
        if metadata.sprint_label:
            # The canonical Sprint.name already carries its own prefix (e.g. "Sprint 24").
            return _inline(metadata.sprint_label)
        sprint_ref = str(metadata.sprint_id) if metadata.sprint_id else "unknown"
        return f"Sprint {sprint_ref}"
    start = _format_datetime(metadata.window_start) if metadata.window_start else "unknown"
    end = _format_datetime(metadata.window_end) if metadata.window_end else "unknown"
    return f"{start} to {end} (date range)"


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _render_summary(report: SectionedReport) -> list[str]:
    counts = report.summary.counts_by_severity
    lines = [
        f"- **{_SEVERITY_LABEL[severity]}:** {counts.get(severity, 0)}"
        for severity in _SUMMARY_SEVERITY_ORDER
    ]
    lines.append(f"- **Total:** {report.summary.total}")
    return lines


def _render_findings(findings: Iterable[SignalFinding]) -> list[str]:
    findings = list(findings)
    if not findings:
        return [_NO_FINDINGS]

    lines: list[str] = []
    for finding in findings:
        lines.append(f"### {_inline(finding.title)}")
        lines.append(f"- **Severity:** {_SEVERITY_LABEL[finding.severity]}")
        lines.append(f"- **Reason:** {_inline(finding.reason)}")
        if finding.recommendation:
            lines.append(f"- **Recommendation:** {_inline(finding.recommendation)}")
        evidence = _format_evidence(finding.evidence)
        if evidence:
            lines.append(f"- **Evidence:** {_inline(evidence)}")
        if finding.source_link:
            lines.append(f"- **Source:** {_link(finding.title, finding.source_link)}")
        lines.append("")
    lines.pop()
    return lines


def _format_evidence(evidence: JsonValue) -> str:
    if isinstance(evidence, dict):
        rendered = ", ".join(f"{key}: {_evidence_value(evidence[key])}" for key in sorted(evidence))
    elif isinstance(evidence, list):
        rendered = ", ".join(_evidence_value(item) for item in evidence)
    elif evidence is None:
        return ""
    else:
        rendered = _evidence_value(evidence)
    return _collapse_ws(rendered)


def _evidence_value(value: JsonValue) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _render_notes(report: SectionedReport) -> list[str]:
    lines: list[str] = []

    if report.skip_notes:
        lines.append("## Skipped Signals")
        lines.append("")
        for note in sorted(report.skip_notes, key=lambda n: (n.signal_id, n.reason)):
            lines.append(f"- **{_inline(note.signal_id)}:** {_inline(note.reason)}")
        lines.append("")

    if report.partial_data_notes:
        lines.append("## Partial Data")
        lines.append("")
        for note in sorted(report.partial_data_notes, key=lambda n: (n.source, n.reason)):
            lines.append(f"- **{_inline(note.source)}:** {_inline(note.reason)}")
        lines.append("")

    return lines


def _collapse_ws(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _inline(text: str) -> str:
    # HTML-escape first, then neutralize Markdown syntax so source text renders literally.
    return _escape_md(html.escape(_collapse_ws(text), quote=False))


def _escape_md(text: str) -> str:
    return text.translate(_MD_ESCAPE)


def _link(text: str, url: str) -> str:
    return f"[{_inline(text)}](<{_collapse_ws(url)}>)"
