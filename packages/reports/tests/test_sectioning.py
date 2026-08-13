from datetime import datetime, timezone
from uuid import UUID, uuid4

from em_radar_core.models import Confidence, EntityType, Severity, SignalFinding
from em_radar_reports import (
    SECTION_ORDER,
    TOP_RISKS_LIMIT,
    PartialDataNote,
    Section,
    SignalMeta,
    SkipNote,
    build_sections,
)

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
REPORT_ID = UUID("11111111-1111-1111-1111-111111111111")


def _finding(
    *,
    signal_id: str,
    signal_name: str,
    severity: Severity,
    entity_type: EntityType,
    title: str,
    recommendation: str | None = None,
) -> SignalFinding:
    return SignalFinding(
        report_id=REPORT_ID,
        signal_id=signal_id,
        signal_name=signal_name,
        severity=severity,
        confidence=Confidence.HIGH,
        entity_type=entity_type,
        entity_id=uuid4(),
        title=title,
        reason="because",
        recommendation=recommendation,
        evidence={},
        created_at=NOW,
    )


def _fixture() -> tuple[list[SignalFinding], dict[str, SignalMeta]]:
    meta = {
        "planning-wi": SignalMeta(category="planning", template_key="story-without-parent-epic"),
        "quality-wi": SignalMeta(
            category="quality", template_key="story-without-acceptance-criteria"
        ),
        "flow-wi": SignalMeta(category="flow", template_key="stale-in-progress-work-item"),
        "delivery-wi": SignalMeta(category="delivery", template_key="repeated-carry-over"),
        "sprint": SignalMeta(category="delivery", template_key="sprint-scope-churn"),
        "linking": SignalMeta(
            category="quality", template_key="mergerequest-without-linked-workitem"
        ),
        "quality-mr": SignalMeta(category="quality", template_key="large-mergerequest-risk"),
        "flow-mr": SignalMeta(category="flow", template_key="mergerequest-waiting-too-long"),
    }
    findings = [
        _finding(
            signal_id="planning-wi",
            signal_name="Story without parent epic",
            severity=Severity.INFO,
            entity_type=EntityType.WORKITEM,
            title="ABC-1 - epic link",
        ),
        _finding(
            signal_id="quality-wi",
            signal_name="Story without acceptance criteria",
            severity=Severity.WARNING,
            entity_type=EntityType.WORKITEM,
            title="ABC-2 - acceptance",
            recommendation="Add acceptance criteria",
        ),
        _finding(
            signal_id="flow-wi",
            signal_name="Stale in-progress work item",
            severity=Severity.WARNING,
            entity_type=EntityType.WORKITEM,
            title="ABC-3 - stale",
        ),
        _finding(
            signal_id="delivery-wi",
            signal_name="Repeated carry-over",
            severity=Severity.WARNING,
            entity_type=EntityType.WORKITEM,
            title="ABC-4 - carryover",
        ),
        _finding(
            signal_id="sprint",
            signal_name="Sprint scope churn",
            severity=Severity.CRITICAL,
            entity_type=EntityType.SPRINT,
            title="Sprint 42",
            recommendation="Freeze sprint scope",
        ),
        _finding(
            signal_id="linking",
            signal_name="Merge request without linked work item",
            severity=Severity.WARNING,
            entity_type=EntityType.MERGEREQUEST,
            title="!10 - unlinked",
        ),
        _finding(
            signal_id="quality-mr",
            signal_name="Large merge request risk",
            severity=Severity.CRITICAL,
            entity_type=EntityType.MERGEREQUEST,
            title="!11 - large",
            recommendation="Split this MR",
        ),
        _finding(
            signal_id="flow-mr",
            signal_name="Merge request waiting too long",
            severity=Severity.INFO,
            entity_type=EntityType.MERGEREQUEST,
            title="!12 - waiting",
        ),
    ]
    return findings, meta


def test_all_nine_sections_present_and_ordered() -> None:
    findings, meta = _fixture()
    report = build_sections(findings, meta)

    assert [s.section for s in report.sections] == list(SECTION_ORDER)
    assert len(report.sections) == 9


def test_findings_assigned_to_expected_themed_sections() -> None:
    findings, meta = _fixture()
    report = build_sections(findings, meta)

    def titles(section: Section) -> set[str]:
        return {f.title for f in report.get_section(section).findings}

    assert titles(Section.PLANNING_HYGIENE) == {"ABC-1 - epic link", "ABC-2 - acceptance"}
    assert titles(Section.DELIVERY_FLOW) == {"ABC-3 - stale", "ABC-4 - carryover"}
    assert titles(Section.SPRINT_HEALTH) == {"Sprint 42"}
    assert titles(Section.MERGE_REQUEST_FLOW) == {"!11 - large", "!12 - waiting"}
    assert titles(Section.SOURCE_LINKING) == {"!10 - unlinked"}


def test_severity_ordered_within_sections() -> None:
    findings, meta = _fixture()
    report = build_sections(findings, meta)

    for section in report.sections:
        severities = [f.severity for f in section.findings]
        ranks = [
            {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}[s] for s in severities
        ]
        assert ranks == sorted(ranks)


def test_top_risks_are_highest_severity_capped() -> None:
    findings, meta = _fixture()
    report = build_sections(findings, meta)

    top = report.get_section(Section.TOP_RISKS).findings
    assert len(top) <= TOP_RISKS_LIMIT
    # Both critical findings must lead the list.
    assert top[0].severity is Severity.CRITICAL
    assert top[1].severity is Severity.CRITICAL
    critical_titles = {f.title for f in top[:2]}
    assert critical_titles == {"Sprint 42", "!11 - large"}


def test_summary_counts_correct() -> None:
    findings, meta = _fixture()
    report = build_sections(findings, meta)

    assert report.summary.total == 8
    assert report.summary.counts_by_severity[Severity.CRITICAL] == 2
    assert report.summary.counts_by_severity[Severity.WARNING] == 4
    assert report.summary.counts_by_severity[Severity.INFO] == 2


def test_suggested_actions_only_recommendation_bearing() -> None:
    findings, meta = _fixture()
    report = build_sections(findings, meta)

    titles = [f.title for f in report.get_section(Section.SUGGESTED_ACTIONS).findings]
    assert set(titles) == {"Sprint 42", "!11 - large", "ABC-2 - acceptance"}
    assert titles[0] in {"Sprint 42", "!11 - large"}  # criticals first


def test_detailed_findings_contains_all() -> None:
    findings, meta = _fixture()
    report = build_sections(findings, meta)

    assert len(report.get_section(Section.DETAILED_FINDINGS).findings) == len(findings)


def test_skip_and_partial_data_notes_carried() -> None:
    findings, meta = _fixture()
    report = build_sections(
        findings,
        meta,
        skip_notes=[SkipNote(signal_id="sprint", reason="requires a sprint window")],
        partial_data_notes=[PartialDataNote(source="code", reason="code data unavailable")],
    )

    assert report.skip_notes == [SkipNote(signal_id="sprint", reason="requires a sprint window")]
    assert report.partial_data_notes == [
        PartialDataNote(source="code", reason="code data unavailable")
    ]


def test_deterministic_regardless_of_input_order() -> None:
    findings, meta = _fixture()
    forward = build_sections(findings, meta)
    reversed_report = build_sections(list(reversed(findings)), meta)
    repeat = build_sections(findings, meta)

    assert forward == reversed_report
    assert forward == repeat


def test_missing_metadata_falls_back_by_entity() -> None:
    finding = _finding(
        signal_id="mystery",
        signal_name="Mystery signal",
        severity=Severity.WARNING,
        entity_type=EntityType.MERGEREQUEST,
        title="!99 - mystery",
    )
    report = build_sections([finding], {})

    assert {f.title for f in report.get_section(Section.MERGE_REQUEST_FLOW).findings} == {
        "!99 - mystery"
    }
    assert len(report.get_section(Section.DETAILED_FINDINGS).findings) == 1


def test_unknown_category_with_meta_present_falls_back_by_entity() -> None:
    finding = _finding(
        signal_id="mystery",
        signal_name="Mystery signal",
        severity=Severity.WARNING,
        entity_type=EntityType.WORKITEM,
        title="ABC-9 - mystery",
    )
    report = build_sections([finding], {"mystery": SignalMeta(category="unknown")})

    assert {f.title for f in report.get_section(Section.DELIVERY_FLOW).findings} == {
        "ABC-9 - mystery"
    }
    assert len(report.get_section(Section.DETAILED_FINDINGS).findings) == 1


def test_hygiene_category_routes_to_planning_hygiene() -> None:
    finding = _finding(
        signal_id="ui-hygiene",
        signal_name="UI hygiene signal",
        severity=Severity.WARNING,
        entity_type=EntityType.WORKITEM,
        title="ABC-7 - hygiene",
    )
    report = build_sections([finding], {"ui-hygiene": SignalMeta(category="hygiene")})

    assert {f.title for f in report.get_section(Section.PLANNING_HYGIENE).findings} == {
        "ABC-7 - hygiene"
    }


def test_sprint_category_routes_to_sprint_health() -> None:
    finding = _finding(
        signal_id="ui-sprint",
        signal_name="UI sprint signal",
        severity=Severity.WARNING,
        entity_type=EntityType.WORKITEM,
        title="ABC-8 - sprint category",
    )
    report = build_sections([finding], {"ui-sprint": SignalMeta(category="sprint")})

    assert {f.title for f in report.get_section(Section.SPRINT_HEALTH).findings} == {
        "ABC-8 - sprint category"
    }


def test_sprint_entity_with_flow_category_routes_to_sprint_health() -> None:
    finding = _finding(
        signal_id="sprint-flow",
        signal_name="Sprint flow signal",
        severity=Severity.WARNING,
        entity_type=EntityType.SPRINT,
        title="Sprint 7",
    )
    report = build_sections([finding], {"sprint-flow": SignalMeta(category="flow")})

    assert {f.title for f in report.get_section(Section.SPRINT_HEALTH).findings} == {"Sprint 7"}


def test_recreated_source_linking_without_template_key() -> None:
    finding = _finding(
        signal_id="recreated-linking",
        signal_name="Merge request without linked work item",
        severity=Severity.WARNING,
        entity_type=EntityType.MERGEREQUEST,
        title="!20 - unlinked recreated",
    )
    report = build_sections(
        [finding],
        {"recreated-linking": SignalMeta(category="quality", is_source_linking=True)},
    )

    assert {f.title for f in report.get_section(Section.SOURCE_LINKING).findings} == {
        "!20 - unlinked recreated"
    }
    assert report.get_section(Section.MERGE_REQUEST_FLOW).findings == []


def test_empty_findings_yields_all_sections_empty() -> None:
    report = build_sections([], {})

    assert [s.section for s in report.sections] == list(SECTION_ORDER)
    assert all(section.findings == [] for section in report.sections)
    assert report.summary.total == 0
    assert report.summary.counts_by_severity == {
        Severity.CRITICAL: 0,
        Severity.WARNING: 0,
        Severity.INFO: 0,
    }


def test_tie_break_is_stable_across_input_order() -> None:
    first = _finding(
        signal_id="tie",
        signal_name="Same signal",
        severity=Severity.WARNING,
        entity_type=EntityType.WORKITEM,
        title="Same title",
    )
    second = _finding(
        signal_id="tie",
        signal_name="Same signal",
        severity=Severity.WARNING,
        entity_type=EntityType.WORKITEM,
        title="Same title",
    )

    forward = build_sections([first, second], {}).get_section(Section.DELIVERY_FLOW).findings
    reversed_run = build_sections([second, first], {}).get_section(Section.DELIVERY_FLOW).findings

    assert [f.entity_id for f in forward] == [f.entity_id for f in reversed_run]
    # entity_id is the only differing field, so it must decide the order.
    assert [f.entity_id for f in forward] == sorted((first.entity_id, second.entity_id), key=str)
