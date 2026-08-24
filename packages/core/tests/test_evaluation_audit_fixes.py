# SPDX-License-Identifier: Apache-2.0
"""Regression tests for evaluation-engine audit fixes.

- Non-numeric / boolean observed values on numeric operators must produce a no-match
  instead of raising and aborting the whole report.
- Sprint scope-churn math must tolerate tz-naive datetimes rather than raising TypeError.
"""

from datetime import datetime, timezone
from uuid import uuid4

from em_radar_core.evaluation import ScopeDescriptor, evaluate_signal_definition
from em_radar_core.evaluation import declarative as _declarative
from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, context, project, sprint, workitem

_SCHEMA = JiraConnector.describe_signal_schema()


def _definition(expression: dict[str, object]) -> SignalDefinition:
    return SignalDefinition(
        name="Audit fix test",
        entity_type="issue",
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="hygiene"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _scope() -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Platform",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "PLAT"},
        capabilities=("statuses",),
    )


def _data(item) -> SignalData:
    return SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,))


def _greater_than(value: object) -> dict[str, object]:
    return {
        "type": "group",
        "operator": "all",
        "conditions": [{"field": "customfield_10100", "operator": "greater_than", "value": value}],
    }


class TestNonNumericComparisonDoesNotAbort:
    def test_string_custom_field_greater_than_yields_no_match(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10100": "N/A"}
        findings = evaluate_signal_definition(
            _definition(_greater_than(5)), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert findings == []

    def test_boolean_custom_field_not_treated_as_numeric(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10100": True}
        findings = evaluate_signal_definition(
            _definition(_greater_than(0)), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert findings == []

    def test_numeric_custom_field_still_matches(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10100": 80.0}
        findings = evaluate_signal_definition(
            _definition(_greater_than(50)), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1


class TestCompareNumericTolerance:
    def test_numeric_or_none_rejects_bool_and_strings(self) -> None:
        assert _declarative._numeric_or_none(True) is None
        assert _declarative._numeric_or_none("5") is None
        assert _declarative._numeric_or_none(None) is None
        assert _declarative._numeric_or_none(7) == 7.0
        assert _declarative._numeric_or_none(3.5) == 3.5

    def test_compare_numeric_operators_on_non_numeric_are_false(self) -> None:
        assert _declarative._compare("N/A", "greater_than", 5) is False
        assert _declarative._compare(True, "gt", 0) is False
        assert _declarative._compare(10, "greater_than", 5) is True


class TestSprintChurnTzNaive:
    def test_churn_with_naive_datetimes_does_not_raise(self) -> None:
        board_sprint = sprint(start_date=datetime(2026, 1, 10, 12))  # tz-naive on purpose
        item = workitem(
            sprint_ids=[board_sprint.id],
            created_at=datetime(2026, 1, 5, 12),  # tz-naive, before sprint start
        )
        data = SignalData(
            report_id=uuid4(),
            projects=(project(),),
            sprints=(board_sprint,),
            workitems=(item,),
        )
        # NOW is tz-aware; before the fix this mixed tz-aware/naive and raised TypeError.
        result = _declarative._sprint_scope_churn(board_sprint, data, context())
        assert result is not None
        assert result.original_count == 1

    def test_first_seen_at_normalizes_to_utc(self) -> None:
        item = workitem(created_at=datetime(2026, 1, 5, 12))  # naive
        data = SignalData(report_id=uuid4(), projects=(project(),), workitems=(item,))
        first_seen = _declarative._first_seen_at(item, data)
        assert first_seen is not None
        assert first_seen.tzinfo is timezone.utc
