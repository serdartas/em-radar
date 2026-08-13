import json
import re
from collections.abc import Iterable

from em_radar_core.models import Severity, SignalFinding
from pydantic import JsonValue

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

_NO_FINDINGS: str = "_No findings._"

_WHITESPACE = re.compile(r"\s+")


def render_markdown(report: SectionedReport) -> str:
    """Render a sectioned report to portable, deterministic Markdown.

    The same `SectionedReport` always renders byte-identically: findings keep the
    severity order M6-01 already applied, summary counts render in a fixed order,
    evidence keys are sorted, and skip/partial-data notes are sorted before output.
    Finding text is sanitized (whitespace collapsed, link syntax escaped, URLs
    angle-bracket wrapped) so titles or reasons carrying Markdown metacharacters or
    newlines cannot break a link or split a list item. Only stdlib and
    `em_radar_core` are used, keeping the reports package source-agnostic.
    """
    lines: list[str] = [f"# {REPORT_TITLE}", ""]

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
            lines.append(f"- **Evidence:** {evidence}")
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
    return _inline(rendered)


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


def _inline(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _link(text: str, url: str) -> str:
    return f"[{_escape_link_text(text)}](<{_inline(url)}>)"


def _escape_link_text(text: str) -> str:
    return _inline(text).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
