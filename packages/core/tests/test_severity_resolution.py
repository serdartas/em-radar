"""Tests for the canonical severity resolution order (signal spec §8).

Pack-level and template-tier resolution is applied at seed/import time (apply_pack_defaults,
signal catalog). By the time a signal reaches the evaluator its report_settings.severity already
holds the fully resolved value. The evaluator reads that value via resolve_severity, which is also
the single point used by callers that construct resolution before calling the evaluator.
"""

from datetime import timedelta
from uuid import uuid4

from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition, resolve_severity
from em_radar_core.models import ReportSettings, Severity, SignalDefinition, SignalOrigin
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, context, project, workitem


def _scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Radar",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "RAD", "name": "Radar"},
        capabilities=("statuses", "labels"),
    )


def _definition(severity: str = "warning") -> SignalDefinition:
    return SignalDefinition(
        name="Severity resolution test",
        entity_type="issue",
        expression={
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "status_category", "operator": "is", "value": "in_progress"},
            ],
        },
        report_settings=ReportSettings(severity=severity, category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


# ---------------------------------------------------------------------------
# resolve_severity unit tests — each precedence layer wins in order
# ---------------------------------------------------------------------------


def test_per_signal_severity_wins_over_pack_override_and_template() -> None:
    result = resolve_severity("info", pack_override="warning", template_default="critical")
    assert result is Severity.INFO


def test_pack_override_applies_when_no_per_signal_severity() -> None:
    result = resolve_severity(None, pack_override="critical", template_default="warning")
    assert result is Severity.CRITICAL


def test_template_default_applies_when_per_signal_and_pack_are_absent() -> None:
    result = resolve_severity(None, pack_override=None, template_default="info")
    assert result is Severity.INFO


def test_fallback_to_warning_when_all_tiers_absent() -> None:
    result = resolve_severity(None, pack_override=None, template_default=None)
    assert result is Severity.WARNING


def test_per_signal_beats_pack_override() -> None:
    result = resolve_severity("info", pack_override="critical")
    assert result is Severity.INFO


def test_per_signal_beats_template_default() -> None:
    result = resolve_severity("info", template_default="critical")
    assert result is Severity.INFO


def test_pack_override_beats_template_default() -> None:
    result = resolve_severity(None, pack_override="info", template_default="critical")
    assert result is Severity.INFO


# ---------------------------------------------------------------------------
# Evaluator integration: reads pre-resolved severity from report_settings
# ---------------------------------------------------------------------------


def test_evaluator_emits_severity_from_report_settings() -> None:
    """The evaluator's only severity source is report_settings.severity (already resolved)."""
    item = workitem(key="RAD-1")
    findings = evaluate_signal_definition(
        _definition(severity="info"),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 1
    assert findings[0].severity is Severity.INFO


def test_evaluator_emits_critical_when_report_settings_severity_is_critical() -> None:
    item = workitem(key="RAD-1")
    findings = evaluate_signal_definition(
        _definition(severity="critical"),
        SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,)),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert findings[0].severity is Severity.CRITICAL


# ---------------------------------------------------------------------------
# No self-escalation: severity is stable regardless of observed values
# ---------------------------------------------------------------------------


def test_severity_does_not_change_with_different_observed_values() -> None:
    """Severity is a fixed configuration property; different matching items must produce the same severity."""
    stale_5_days = workitem(
        key="RAD-1", updated_at=NOW - timedelta(days=5), created_at=NOW - timedelta(days=10)
    )
    stale_30_days = workitem(
        key="RAD-2", updated_at=NOW - timedelta(days=30), created_at=NOW - timedelta(days=35)
    )
    expression = {
        "type": "group",
        "operator": "all",
        "conditions": [
            {"field": "status_category", "operator": "is", "value": "in_progress"},
            {
                "field": "age_since_updated",
                "operator": "greater_than",
                "value": {"amount": 3, "unit": "days"},
            },
        ],
    }
    definition = SignalDefinition(
        name="Stale test",
        entity_type="issue",
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="flow"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )

    findings = evaluate_signal_definition(
        definition,
        SignalData(
            report_id=uuid4(),
            projects=(project(),),
            workitems=(stale_5_days, stale_30_days),
        ),
        context(),
        JiraConnector.describe_signal_schema(),
        [_scope()],
    )

    assert len(findings) == 2
    severities = {f.severity for f in findings}
    assert severities == {Severity.WARNING}, "all findings must carry the same fixed severity"
