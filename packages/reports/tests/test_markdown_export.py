from datetime import datetime, timezone
from uuid import UUID

from em_radar_core.models import (
    Confidence,
    EntityType,
    ReportStatus,
    Severity,
    SignalFinding,
    WindowType,
)
from em_radar_reports import (
    PartialDataNote,
    ReportMetadata,
    Section,
    SignalMeta,
    SkipNote,
    build_sections,
    render_markdown,
)
from em_radar_reports.markdown_export import _format_evidence

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
REPORT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEAM_ID = UUID("22222222-2222-2222-2222-222222222222")
SPRINT_ID = UUID("33333333-3333-3333-3333-333333333333")


def _metadata() -> ReportMetadata:
    return ReportMetadata(
        report_id=REPORT_ID,
        generated_at=NOW,
        status=ReportStatus.SUCCEEDED,
        window_type=WindowType.DATE_RANGE,
        team_name="Platform",
        team_id=TEAM_ID,
        window_start=datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 8, 13, 0, 0, 0, tzinfo=timezone.utc),
    )


def _finding(
    *,
    signal_id: str,
    signal_name: str,
    severity: Severity,
    entity_type: EntityType,
    title: str,
    entity_id: str,
    reason: str = "because",
    recommendation: str | None = None,
    evidence: dict[str, object] | None = None,
    source_link: str | None = None,
) -> SignalFinding:
    return SignalFinding(
        report_id=REPORT_ID,
        signal_id=signal_id,
        signal_name=signal_name,
        severity=severity,
        confidence=Confidence.HIGH,
        entity_type=entity_type,
        entity_id=UUID(entity_id),
        title=title,
        reason=reason,
        recommendation=recommendation,
        evidence=evidence or {},
        source_link=source_link,
        created_at=NOW,
    )


def _demo_report():
    meta = {
        "planning-wi": SignalMeta(category="planning", template_key="story-without-parent-epic"),
        "flow-wi": SignalMeta(category="flow", template_key="stale-in-progress-work-item"),
        "sprint": SignalMeta(category="sprint", template_key="sprint-scope-churn"),
        "flow-mr": SignalMeta(category="flow", template_key="mergerequest-waiting-too-long"),
        "linking": SignalMeta(
            category="quality", template_key="mergerequest-without-linked-workitem"
        ),
    }
    findings = [
        _finding(
            signal_id="flow-mr",
            signal_name="Merge request waiting too long",
            severity=Severity.CRITICAL,
            entity_type=EntityType.MERGEREQUEST,
            title="!42 - refactor pipeline",
            entity_id="00000000-0000-0000-0000-000000000001",
            reason="Open 12 days without review",
            recommendation="Request a reviewer",
            evidence={"open_days": 12, "reviewers": 0},
            source_link="https://gitlab.example.com/team/repo/-/merge_requests/42",
        ),
        _finding(
            signal_id="flow-wi",
            signal_name="Stale in-progress work item",
            severity=Severity.WARNING,
            entity_type=EntityType.WORKITEM,
            title="ABC-3 - stale story",
            entity_id="00000000-0000-0000-0000-000000000002",
            reason="In progress for 9 days",
            recommendation="Split or re-scope the story",
            evidence={"age_days": 9},
            source_link="https://jira.example.com/browse/ABC-3",
        ),
        _finding(
            signal_id="planning-wi",
            signal_name="Story without parent epic",
            severity=Severity.INFO,
            entity_type=EntityType.WORKITEM,
            title="ABC-1 - orphan story",
            entity_id="00000000-0000-0000-0000-000000000003",
            reason="No parent epic linked",
            evidence={},
            source_link="https://jira.example.com/browse/ABC-1",
        ),
        _finding(
            signal_id="sprint",
            signal_name="Sprint scope churn",
            severity=Severity.WARNING,
            entity_type=EntityType.SPRINT,
            title="Sprint 7 - scope churn",
            entity_id="00000000-0000-0000-0000-000000000004",
            reason="Scope changed by 40% mid-sprint",
            evidence={"churn_pct": 40},
            source_link="https://jira.example.com/sprint/7",
        ),
        _finding(
            signal_id="linking",
            signal_name="Merge request without linked work item",
            severity=Severity.INFO,
            entity_type=EntityType.MERGEREQUEST,
            title="!43 - hotfix",
            entity_id="00000000-0000-0000-0000-000000000005",
            reason="No linked work item",
            recommendation="Link the merge request to its work item",
            evidence={"linked_workitem_keys": []},
            source_link="https://gitlab.example.com/team/repo/-/merge_requests/43",
        ),
    ]
    return build_sections(
        findings,
        meta,
        skip_notes=[SkipNote(signal_id="sprint-velocity", reason="No closed sprints in window")],
        partial_data_notes=[PartialDataNote(source="gitlab", reason="Rate limited")],
    )


def test_all_nine_section_headings_present() -> None:
    markdown = render_markdown(_demo_report(), _metadata())
    for section in Section:
        assert f"## {section.title}" in markdown


def test_severity_order_preserved_within_detailed_findings() -> None:
    markdown = render_markdown(_demo_report(), _metadata())
    critical = markdown.index("!42 - refactor pipeline")
    warning = markdown.index("ABC-3 - stale story")
    info = markdown.index("ABC-1 - orphan story")
    assert critical < warning < info


def test_every_finding_has_a_resolvable_source_link() -> None:
    report = _demo_report()
    markdown = render_markdown(report, _metadata())
    source_lines = [line for line in markdown.splitlines() if line.startswith("- **Source:**")]
    # Detailed Findings holds one entry per finding; each renders exactly one link
    # elsewhere too, so at minimum every finding is represented with an http link.
    assert source_lines
    for line in source_lines:
        assert "http" in line
    detailed = report.get_section(Section.DETAILED_FINDINGS).findings
    for finding in detailed:
        assert f"(<{finding.source_link}>)" in markdown
        assert finding.source_link.startswith("http")


def test_missing_source_link_omits_source_line() -> None:
    finding = _finding(
        signal_id="flow-wi",
        signal_name="Stale in-progress work item",
        severity=Severity.WARNING,
        entity_type=EntityType.WORKITEM,
        title="ABC-9 - no link",
        entity_id="00000000-0000-0000-0000-00000000000a",
        source_link=None,
    )
    report = build_sections(
        [finding], {"flow-wi": SignalMeta(category="flow", template_key="stale-in-progress")}
    )
    markdown = render_markdown(report, _metadata())
    assert "ABC-9 - no link" in markdown
    assert "- **Source:**" not in markdown


def test_markdown_special_chars_do_not_break_structure() -> None:
    finding = _finding(
        signal_id="flow-mr",
        signal_name="Merge request waiting too long",
        severity=Severity.CRITICAL,
        entity_type=EntityType.MERGEREQUEST,
        title="!42 - [WIP] fix (auth) | retry\nnow",
        entity_id="00000000-0000-0000-0000-00000000000b",
        reason="Open for a\nlong time",
        evidence={"note": "line1\nline2"},
        source_link="https://gitlab.example.com/mr/42?a=1&b=2",
    )
    report = build_sections(
        [finding],
        {"flow-mr": SignalMeta(category="flow", template_key="mergerequest-waiting-too-long")},
    )
    markdown = render_markdown(report, _metadata())
    assert "(<https://gitlab.example.com/mr/42?a=1&b=2>)" in markdown
    assert r"\[WIP\]" in markdown
    # No raw newline leaks into a heading, reason, or evidence line.
    assert "\nnow" not in markdown
    assert "Open for a\nlong" not in markdown
    assert "line1\nline2" not in markdown
    source_lines = [line for line in markdown.splitlines() if line.startswith("- **Source:**")]
    for line in source_lines:
        assert line.count("](") == 1


def test_html_like_source_text_is_escaped() -> None:
    finding = _finding(
        signal_id="flow-mr",
        signal_name="Merge request waiting too long",
        severity=Severity.CRITICAL,
        entity_type=EntityType.MERGEREQUEST,
        title="!42 - render <Button> & <!-- fix",
        entity_id="00000000-0000-0000-0000-00000000000c",
        reason="Broke <Component> & swallowed <!-- rest",
        recommendation="Wrap <Button> safely",
        evidence={"tag": "<Button> & <!--"},
        source_link="https://gitlab.example.com/mr/42",
    )
    report = build_sections(
        [finding],
        {"flow-mr": SignalMeta(category="flow", template_key="mergerequest-waiting-too-long")},
        skip_notes=[SkipNote(signal_id="s<1>", reason="skipped <because> & more")],
        partial_data_notes=[PartialDataNote(source="git<lab>", reason="rate & limited")],
    )
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        generated_at=NOW,
        status=ReportStatus.SUCCEEDED,
        window_type=WindowType.SPRINT,
        team_name="A & B <Squad>",
        sprint_label="Sprint <7>",
    )
    markdown = render_markdown(report, metadata)

    assert "&lt;Button&gt;" in markdown
    # The comment opener is both HTML-escaped and Markdown-escaped (the bang backslashed).
    assert "&lt;\\!--" in markdown
    assert "&amp;" in markdown
    assert "&lt;Component&gt;" in markdown
    # No active HTML/comment markup survives anywhere in the export.
    assert "<Button>" not in markdown
    assert "<!--" not in markdown
    assert "<Component>" not in markdown
    # Team name and sprint label are escaped too.
    assert "A &amp; B &lt;Squad&gt;" in markdown
    assert "Sprint &lt;7&gt;" in markdown
    # The self-generated link structure and the URL are intact and not corrupted.
    assert "(<https://gitlab.example.com/mr/42>)" in markdown


def test_markdown_syntax_in_source_text_rendered_literally() -> None:
    finding = _finding(
        signal_id="flow-mr",
        signal_name="Merge request waiting too long",
        severity=Severity.CRITICAL,
        entity_type=EntityType.MERGEREQUEST,
        title="!42 - **urgent** [incident](https://example.invalid)",
        entity_id="00000000-0000-0000-0000-00000000000d",
        reason="see `code` and _underscore_ now",
        recommendation="fix **now** [ticket](https://evil.invalid)",
        evidence={"note": "**bold** `x` ~~deprecated~~"},
        source_link="https://gitlab.example.com/mr/42",
    )
    report = build_sections(
        [finding],
        {"flow-mr": SignalMeta(category="flow", template_key="mergerequest-waiting-too-long")},
    )
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        generated_at=NOW,
        status=ReportStatus.SUCCEEDED,
        window_type=WindowType.SPRINT,
        team_name="Team **X** _y_",
        sprint_label="S1",
    )
    markdown = render_markdown(report, metadata)

    assert "\\*\\*urgent\\*\\*" in markdown
    assert "\\[incident\\]" in markdown
    assert "\\`code\\`" in markdown
    assert "\\_underscore\\_" in markdown
    assert "\\~\\~deprecated\\~\\~" in markdown
    assert "Team \\*\\*X\\*\\* \\_y\\_" in markdown
    # No active bold, code span, strikethrough, or injected link from source text.
    assert "**urgent**" not in markdown
    assert "`code`" not in markdown
    assert "~~deprecated~~" not in markdown
    assert "[incident](https://example.invalid)" not in markdown
    assert "https://example.invalid" in markdown  # present, but as inert escaped text
    assert "(https://example.invalid)" not in markdown
    # The self-generated source link structure stays intact.
    assert "](<https://gitlab.example.com/mr/42>)" in markdown


def test_summary_and_notes_rendered() -> None:
    markdown = render_markdown(_demo_report(), _metadata())
    assert "- **Critical:** 1" in markdown
    assert "- **Warning:** 2" in markdown
    assert "- **Info:** 2" in markdown
    assert "- **Total:** 5" in markdown
    assert "## Skipped Signals" in markdown
    assert "- **sprint-velocity:** No closed sprints in window" in markdown
    assert "## Partial Data" in markdown
    assert "- **gitlab:** Rate limited" in markdown


def test_date_range_metadata_block_rendered() -> None:
    markdown = render_markdown(_demo_report(), _metadata())
    assert f"- **Report:** {REPORT_ID}" in markdown
    assert f"- **Team:** Platform ({TEAM_ID})" in markdown
    assert "- **Window:** 2026-08-01T00:00:00+00:00 to 2026-08-13T00:00:00+00:00 (date range)" in (
        markdown
    )
    assert "- **Generated:** 2026-08-13T12:00:00+00:00" in markdown
    # Metadata precedes the sections.
    assert markdown.index("- **Report:**") < markdown.index("## Summary")


def test_sprint_window_metadata_rendered() -> None:
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        generated_at=NOW,
        status=ReportStatus.SUCCEEDED,
        window_type=WindowType.SPRINT,
        team_id=TEAM_ID,
        sprint_id=SPRINT_ID,
        sprint_label="Sprint 7",
    )
    markdown = render_markdown(_demo_report(), metadata)
    # The label carries its own prefix; it must not be doubled to "Sprint Sprint 7".
    assert "- **Window:** Sprint 7\n" in markdown
    assert "Sprint Sprint" not in markdown
    assert f"- **Team:** {TEAM_ID}" in markdown
    assert "to" not in markdown.split("## Summary")[0].split("- **Window:**")[1]


def test_sprint_window_without_label_falls_back_to_id() -> None:
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        generated_at=NOW,
        status=ReportStatus.SUCCEEDED,
        window_type=WindowType.SPRINT,
        sprint_id=SPRINT_ID,
    )
    markdown = render_markdown(build_sections([], {}), metadata)
    assert f"- **Window:** Sprint {SPRINT_ID}" in markdown


def test_naive_generation_timestamp_coerced_to_utc() -> None:
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        generated_at=datetime(2026, 8, 13, 12, 0, 0),
        status=ReportStatus.SUCCEEDED,
        window_type=WindowType.SPRINT,
        sprint_label="S1",
    )
    markdown = render_markdown(build_sections([], {}), metadata)
    assert "- **Generated:** 2026-08-13T12:00:00+00:00" in markdown


def test_failed_report_renders_unmistakable_failure_notice() -> None:
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        generated_at=NOW,
        status=ReportStatus.FAILED,
        window_type=WindowType.DATE_RANGE,
        error="all data sources failed: rate limited",
        window_start=datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 8, 13, 0, 0, 0, tzinfo=timezone.utc),
    )
    markdown = render_markdown(build_sections([], {}), metadata)

    assert "> **This report did not complete successfully.**" in markdown
    assert "> **Status:** Failed" in markdown
    assert "> **Error:** all data sources failed: rate limited" in markdown
    assert "- **Status:** Failed" in markdown
    # The notice precedes the metadata block and the sections.
    assert markdown.index("did not complete successfully") < markdown.index("- **Report:**")
    assert markdown.index("- **Report:**") < markdown.index("## Summary")


def test_succeeded_report_has_no_failure_notice() -> None:
    markdown = render_markdown(_demo_report(), _metadata())
    assert "- **Status:** Succeeded" in markdown
    assert "did not complete successfully" not in markdown


def test_evidence_keys_sorted_deterministically() -> None:
    markdown = render_markdown(_demo_report(), _metadata())
    assert "- **Evidence:** open\\_days: 12, reviewers: 0" in markdown


def test_format_evidence_non_dict_values() -> None:
    assert _format_evidence(["a", "b", 1]) == "a, b, 1"
    assert _format_evidence(7) == "7"
    assert _format_evidence("plain") == "plain"
    assert _format_evidence(None) == ""
    assert _format_evidence({}) == ""
    # Nested containers serialize as sorted JSON, not Python repr.
    assert _format_evidence({"nested": {"b": 2, "a": 1}}) == 'nested: {"a": 1, "b": 2}'
    assert _format_evidence({"items": [1, 2]}) == "items: [1, 2]"


def test_empty_sections_render_placeholder() -> None:
    report = build_sections([], {})
    markdown = render_markdown(report, _metadata())
    for section in Section:
        if section is Section.SUMMARY:
            continue
        assert f"## {section.title}" in markdown
    assert "_No findings._" in markdown
    assert "- **Total:** 0" in markdown


def test_output_is_byte_stable_across_input_orders() -> None:
    report = _demo_report()
    assert render_markdown(report, _metadata()) == render_markdown(report, _metadata())

    meta = {
        "planning-wi": SignalMeta(category="planning", template_key="story-without-parent-epic"),
        "flow-mr": SignalMeta(category="flow", template_key="mergerequest-waiting-too-long"),
    }
    a = _finding(
        signal_id="planning-wi",
        signal_name="Story without parent epic",
        severity=Severity.INFO,
        entity_type=EntityType.WORKITEM,
        title="ABC-1 - orphan",
        entity_id="00000000-0000-0000-0000-000000000101",
        source_link="https://jira.example.com/browse/ABC-1",
    )
    b = _finding(
        signal_id="flow-mr",
        signal_name="Merge request waiting too long",
        severity=Severity.CRITICAL,
        entity_type=EntityType.MERGEREQUEST,
        title="!42 - slow mr",
        entity_id="00000000-0000-0000-0000-000000000102",
        source_link="https://gitlab.example.com/mr/42",
    )
    forward = render_markdown(build_sections([a, b], meta), _metadata())
    reversed_ = render_markdown(build_sections([b, a], meta), _metadata())
    assert forward == reversed_


def test_matches_expected_snapshot() -> None:
    finding = _finding(
        signal_id="flow-mr",
        signal_name="Merge request waiting too long",
        severity=Severity.CRITICAL,
        entity_type=EntityType.MERGEREQUEST,
        title="!42 - refactor pipeline",
        entity_id="00000000-0000-0000-0000-000000000001",
        reason="Open 12 days without review",
        recommendation="Request a reviewer",
        evidence={"open_days": 12, "reviewers": 0},
        source_link="https://gitlab.example.com/mr/42",
    )
    report = build_sections(
        [finding],
        {"flow-mr": SignalMeta(category="flow", template_key="mergerequest-waiting-too-long")},
    )
    expected = (
        "# EM Radar Report\n"
        "\n"
        f"- **Report:** {REPORT_ID}\n"
        f"- **Team:** Platform ({TEAM_ID})\n"
        "- **Window:** 2026-08-01T00:00:00+00:00 to 2026-08-13T00:00:00+00:00 (date range)\n"
        "- **Generated:** 2026-08-13T12:00:00+00:00\n"
        "- **Status:** Succeeded\n"
        "\n"
        "## Summary\n"
        "\n"
        "- **Critical:** 1\n"
        "- **Warning:** 0\n"
        "- **Info:** 0\n"
        "- **Total:** 1\n"
        "\n"
        "## Top Risks\n"
        "\n"
        "### \\!42 - refactor pipeline\n"
        "- **Severity:** Critical\n"
        "- **Reason:** Open 12 days without review\n"
        "- **Recommendation:** Request a reviewer\n"
        "- **Evidence:** open\\_days: 12, reviewers: 0\n"
        "- **Source:** [\\!42 - refactor pipeline](<https://gitlab.example.com/mr/42>)\n"
        "\n"
        "## Planning Hygiene\n"
        "\n"
        "_No findings._\n"
        "\n"
        "## Delivery Flow\n"
        "\n"
        "_No findings._\n"
        "\n"
        "## Sprint Health\n"
        "\n"
        "_No findings._\n"
        "\n"
        "## Merge Request Flow\n"
        "\n"
        "### \\!42 - refactor pipeline\n"
        "- **Severity:** Critical\n"
        "- **Reason:** Open 12 days without review\n"
        "- **Recommendation:** Request a reviewer\n"
        "- **Evidence:** open\\_days: 12, reviewers: 0\n"
        "- **Source:** [\\!42 - refactor pipeline](<https://gitlab.example.com/mr/42>)\n"
        "\n"
        "## Source Linking\n"
        "\n"
        "_No findings._\n"
        "\n"
        "## Detailed Findings\n"
        "\n"
        "### \\!42 - refactor pipeline\n"
        "- **Severity:** Critical\n"
        "- **Reason:** Open 12 days without review\n"
        "- **Recommendation:** Request a reviewer\n"
        "- **Evidence:** open\\_days: 12, reviewers: 0\n"
        "- **Source:** [\\!42 - refactor pipeline](<https://gitlab.example.com/mr/42>)\n"
        "\n"
        "## Suggested Actions\n"
        "\n"
        "### \\!42 - refactor pipeline\n"
        "- **Severity:** Critical\n"
        "- **Reason:** Open 12 days without review\n"
        "- **Recommendation:** Request a reviewer\n"
        "- **Evidence:** open\\_days: 12, reviewers: 0\n"
        "- **Source:** [\\!42 - refactor pipeline](<https://gitlab.example.com/mr/42>)\n"
    )
    assert render_markdown(report, _metadata()) == expected


def test_empty_string_team_field_is_omitted() -> None:
    metadata = ReportMetadata(
        report_id=REPORT_ID,
        generated_at=NOW,
        status=ReportStatus.SUCCEEDED,
        window_type=WindowType.SPRINT,
        sprint_label="S1",
    )
    markdown = render_markdown(build_sections([], {}), metadata)
    assert "- **Team:**" not in markdown
