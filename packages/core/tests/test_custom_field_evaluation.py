# SPDX-License-Identifier: Apache-2.0
"""Tests for custom-field signal evaluation in the declarative engine."""

from uuid import uuid4

import pytest

from em_radar_core.evaluation import (
    ExpressionValidationError,
    ScopeDescriptor,
    evaluate_signal_definition,
    validate_expression,
)
from em_radar_core.evaluation import declarative as _declarative
from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin
from em_radar_core.signals import SignalData
from em_radar_connector_jira.connector import JiraConnector

from _signal_helpers import NOW, context, project, workitem


_SCHEMA = JiraConnector.describe_signal_schema()


def _definition(expression: dict[str, object]) -> SignalDefinition:
    return SignalDefinition(
        name="Custom field test",
        entity_type="issue",
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="hygiene"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _scope(capabilities: tuple[str, ...] = ("statuses",)) -> ScopeDescriptor:
    return ScopeDescriptor(
        connector_id="jira-1",
        scope_id="scope-1",
        scope_type="project",
        name="Platform",
        external_ref={"type": "jira_project", "id": "PROJECT", "key": "PLAT"},
        capabilities=capabilities,
    )


def _data(item) -> SignalData:
    return SignalData(
        report_id=uuid4(),
        projects=(project(),),
        workitems=(item,),
    )


# ---------------------------------------------------------------------------
# validate_expression — custom-field condition acceptance
# ---------------------------------------------------------------------------


class TestValidateConditionCustomField:
    def test_valid_custom_field_condition_does_not_raise(self) -> None:
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "customfield_10100", "operator": "is", "value": "Backend"}],
        }
        validate_expression(expression, _SCHEMA, [_scope()])  # must not raise

    def test_invalid_operator_for_custom_field_raises(self) -> None:
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "customfield_10100", "operator": "matches_glob", "value": "back*"}
            ],
        }
        with pytest.raises(ExpressionValidationError, match="customfield_10100"):
            validate_expression(expression, _SCHEMA, [_scope()])

    def test_builtin_field_collision_guard_uses_builtin_schema(self) -> None:
        """A key that looks like a custom field but matches a built-in is validated as built-in."""
        # "status" is a built-in — using a custom-field-only operator should raise.
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [
                # "greater_than" is not valid for built-in "status"
                {"field": "status", "operator": "greater_than", "value": "In Progress"}
            ],
        }
        with pytest.raises(ExpressionValidationError, match="status"):
            validate_expression(expression, _SCHEMA, [_scope()])


# ---------------------------------------------------------------------------
# _field_value — custom field retrieval
# ---------------------------------------------------------------------------


class TestFieldValueCustomField:
    def test_returns_custom_field_value_when_present(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10100": 42.0}
        val = _declarative._field_value("customfield_10100", item, _data(item), context(), _scope())
        assert val == 42.0

    def test_returns_none_when_custom_field_absent(self) -> None:
        item = workitem()
        item.custom_fields = {}
        val = _declarative._field_value("customfield_10100", item, _data(item), context(), _scope())
        assert val is None

    def test_builtin_status_not_overridden_by_custom_fields(self) -> None:
        """Even if custom_fields has a "status" key, _field_value returns the model attribute."""
        item = workitem(status="In Progress")
        item.custom_fields = {"status": "FAKE"}
        val = _declarative._field_value("status", item, _data(item), context(), _scope())
        assert val == "In Progress"


# ---------------------------------------------------------------------------
# evaluate_signal_definition — end-to-end custom field evaluation
# ---------------------------------------------------------------------------


class TestEvaluateCustomFieldSignal:
    def test_number_field_greater_than_matches(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10100": 80.0}
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "customfield_10100", "operator": "greater_than", "value": 50}],
        }
        findings = evaluate_signal_definition(
            _definition(expression), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1

    def test_number_field_greater_than_no_match(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10100": 20.0}
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "customfield_10100", "operator": "greater_than", "value": 50}],
        }
        findings = evaluate_signal_definition(
            _definition(expression), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 0

    def test_unpopulated_field_matches_is_empty(self) -> None:
        item = workitem()
        item.custom_fields = {}
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "customfield_10100", "operator": "is_empty"}],
        }
        findings = evaluate_signal_definition(
            _definition(expression), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1

    def test_array_field_contains_matches(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10200": ["Backend", "Platform"]}
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "customfield_10200", "operator": "contains", "value": "Backend"}
            ],
        }
        findings = evaluate_signal_definition(
            _definition(expression), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1

    def test_array_field_does_not_contain_matches(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10200": ["Frontend"]}
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "customfield_10200", "operator": "does_not_contain", "value": "Backend"}
            ],
        }
        findings = evaluate_signal_definition(
            _definition(expression), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1

    def test_string_is_not_empty_matches_when_value_set(self) -> None:
        item = workitem()
        item.custom_fields = {"customfield_10300": "some value"}
        expression = {
            "type": "group",
            "operator": "all",
            "conditions": [{"field": "customfield_10300", "operator": "is_not_empty"}],
        }
        findings = evaluate_signal_definition(
            _definition(expression), _data(item), context(), _SCHEMA, [_scope()]
        )
        assert len(findings) == 1
