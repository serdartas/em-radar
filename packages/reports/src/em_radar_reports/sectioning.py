from collections.abc import Mapping, Sequence
from enum import StrEnum

from em_radar_core.models import EntityType, Severity, SignalFinding
from pydantic import BaseModel, Field

# Template keys whose findings belong in the Source Linking section. Kept as a
# configurable set (not an inline literal) so the source-linking rule is not a
# fragile string comparison scattered through the assignment logic.
SOURCE_LINKING_TEMPLATE_KEYS: frozenset[str] = frozenset({"mergerequest-without-linked-workitem"})

# Top Risks surfaces the most urgent items at a glance; 5 keeps the section a
# scannable "read these first" list rather than a duplicate of Detailed Findings.
TOP_RISKS_LIMIT: int = 5


class Section(StrEnum):
    SUMMARY = "summary"
    TOP_RISKS = "top_risks"
    PLANNING_HYGIENE = "planning_hygiene"
    DELIVERY_FLOW = "delivery_flow"
    SPRINT_HEALTH = "sprint_health"
    MERGE_REQUEST_FLOW = "merge_request_flow"
    SOURCE_LINKING = "source_linking"
    DETAILED_FINDINGS = "detailed_findings"
    SUGGESTED_ACTIONS = "suggested_actions"

    @property
    def title(self) -> str:
        return _SECTION_TITLES[self]


_SECTION_TITLES: dict[Section, str] = {
    Section.SUMMARY: "Summary",
    Section.TOP_RISKS: "Top Risks",
    Section.PLANNING_HYGIENE: "Planning Hygiene",
    Section.DELIVERY_FLOW: "Delivery Flow",
    Section.SPRINT_HEALTH: "Sprint Health",
    Section.MERGE_REQUEST_FLOW: "Merge Request Flow",
    Section.SOURCE_LINKING: "Source Linking",
    Section.DETAILED_FINDINGS: "Detailed Findings",
    Section.SUGGESTED_ACTIONS: "Suggested Actions",
}

# Canonical render order for all nine sections.
SECTION_ORDER: tuple[Section, ...] = (
    Section.SUMMARY,
    Section.TOP_RISKS,
    Section.PLANNING_HYGIENE,
    Section.DELIVERY_FLOW,
    Section.SPRINT_HEALTH,
    Section.MERGE_REQUEST_FLOW,
    Section.SOURCE_LINKING,
    Section.DETAILED_FINDINGS,
    Section.SUGGESTED_ACTIONS,
)

_THEMED_SECTIONS: tuple[Section, ...] = (
    Section.PLANNING_HYGIENE,
    Section.DELIVERY_FLOW,
    Section.SPRINT_HEALTH,
    Section.MERGE_REQUEST_FLOW,
    Section.SOURCE_LINKING,
)

# Critical outranks warning outranks info; lower rank sorts first.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.WARNING: 1,
    Severity.INFO: 2,
}

# Fallback themed section by entity when a finding's (category, entity) matches no
# rule (e.g. an unknown category or missing metadata). The finding still appears
# in Detailed Findings; this only picks a themed home so nothing is dropped.
_FALLBACK_SECTION_BY_ENTITY: dict[EntityType, Section] = {
    EntityType.WORKITEM: Section.DELIVERY_FLOW,
    EntityType.MERGEREQUEST: Section.MERGE_REQUEST_FLOW,
    EntityType.SPRINT: Section.SPRINT_HEALTH,
    EntityType.REPOSITORY: Section.MERGE_REQUEST_FLOW,
}


class SignalMeta(BaseModel):
    """Per-signal metadata the caller supplies for section assignment.

    A SignalFinding does not carry its signal's category or template key, so the
    caller maps each signal_id to these values (from the SignalDefinition).
    """

    category: str
    template_key: str | None = None


class SkipNote(BaseModel):
    """A signal that did not run, and why (window gating, capability, absent source)."""

    signal_id: str
    reason: str


class PartialDataNote(BaseModel):
    """A data source that failed or returned partial data, and why."""

    source: str
    reason: str


class ReportSummary(BaseModel):
    counts_by_severity: dict[Severity, int] = Field(
        default_factory=lambda: {severity: 0 for severity in Severity}
    )
    total: int = 0


class ReportSection(BaseModel):
    section: Section
    title: str
    findings: list[SignalFinding] = Field(default_factory=list)


class SectionedReport(BaseModel):
    summary: ReportSummary
    sections: list[ReportSection]
    skip_notes: list[SkipNote] = Field(default_factory=list)
    partial_data_notes: list[PartialDataNote] = Field(default_factory=list)

    def get_section(self, section: Section) -> ReportSection:
        for report_section in self.sections:
            if report_section.section is section:
                return report_section
        raise KeyError(section)


def _sort_key(finding: SignalFinding) -> tuple[int, str, str, str]:
    return (
        _SEVERITY_RANK[finding.severity],
        finding.signal_name,
        finding.title,
        str(finding.entity_id),
    )


def assign_section(finding: SignalFinding, meta: SignalMeta | None) -> Section:
    """Return the themed section a finding belongs to (see the M6-01 rule table)."""
    entity = finding.entity_type
    if meta is not None:
        category = meta.category
        # First match wins; order matches the decided rule table exactly.
        if category == "planning":
            return Section.PLANNING_HYGIENE
        if category == "quality" and entity is EntityType.WORKITEM:
            return Section.PLANNING_HYGIENE
        if category == "flow" and entity is EntityType.WORKITEM:
            return Section.DELIVERY_FLOW
        if category == "delivery" and entity is EntityType.WORKITEM:
            return Section.DELIVERY_FLOW
        if entity is EntityType.SPRINT:
            return Section.SPRINT_HEALTH
        if meta.template_key in SOURCE_LINKING_TEMPLATE_KEYS:
            return Section.SOURCE_LINKING
        if category == "quality" and entity is EntityType.MERGEREQUEST:
            return Section.MERGE_REQUEST_FLOW
        if category == "flow" and entity is EntityType.MERGEREQUEST:
            return Section.MERGE_REQUEST_FLOW
    return _FALLBACK_SECTION_BY_ENTITY.get(entity, Section.DELIVERY_FLOW)


def build_sections(
    findings: Sequence[SignalFinding],
    signal_meta_by_id: Mapping[str, SignalMeta],
    *,
    skip_notes: Sequence[SkipNote] | None = None,
    partial_data_notes: Sequence[PartialDataNote] | None = None,
) -> SectionedReport:
    """Group findings into the nine canonical report sections, severity-ordered.

    Output is fully deterministic: findings are sorted by (severity, signal_name,
    title, entity_id) so identical inputs always produce equal reports regardless
    of the order findings are supplied in.
    """
    ordered = sorted(findings, key=_sort_key)

    themed: dict[Section, list[SignalFinding]] = {section: [] for section in _THEMED_SECTIONS}
    for finding in ordered:
        section = assign_section(finding, signal_meta_by_id.get(finding.signal_id))
        themed[section].append(finding)

    counts = {severity: 0 for severity in Severity}
    for finding in ordered:
        counts[finding.severity] += 1
    summary = ReportSummary(counts_by_severity=counts, total=len(ordered))

    top_risks = ordered[:TOP_RISKS_LIMIT]
    suggested = [finding for finding in ordered if finding.recommendation]

    section_findings: dict[Section, list[SignalFinding]] = {
        Section.SUMMARY: [],
        Section.TOP_RISKS: top_risks,
        **themed,
        Section.DETAILED_FINDINGS: ordered,
        Section.SUGGESTED_ACTIONS: suggested,
    }

    sections = [
        ReportSection(
            section=section,
            title=section.title,
            findings=list(section_findings[section]),
        )
        for section in SECTION_ORDER
    ]

    return SectionedReport(
        summary=summary,
        sections=sections,
        skip_notes=list(skip_notes or []),
        partial_data_notes=list(partial_data_notes or []),
    )
