"""Tests for is_source_linking_signal — detecting link-emptiness expressions (M6-07)."""

from em_radar_core.evaluation import is_source_linking_signal
from em_radar_core.models import ReportSettings, SignalDefinition, SignalOrigin

from _signal_helpers import NOW


def _signal(expression: object) -> SignalDefinition:
    return SignalDefinition(
        name="Test signal",
        entity_type="merge_request",
        expression=expression,
        report_settings=ReportSettings(severity="warning", category="quality"),
        enabled=True,
        origin=SignalOrigin.USER_CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def test_true_for_link_emptiness_expression() -> None:
    definition = _signal(
        {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "state", "operator": "is", "value": "open"},
                {"field": "linked_workitem_keys", "operator": "is_empty"},
            ],
        }
    )
    assert is_source_linking_signal(definition) is True


def test_false_for_unrelated_expression() -> None:
    definition = _signal(
        {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "state", "operator": "is", "value": "open"},
            ],
        }
    )
    assert is_source_linking_signal(definition) is False


def test_false_when_field_matches_but_operator_differs() -> None:
    definition = _signal(
        {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "linked_workitem_keys", "operator": "is_not_empty"},
            ],
        }
    )
    assert is_source_linking_signal(definition) is False


def test_false_when_expression_is_not_a_dict() -> None:
    definition = _signal(None)
    assert is_source_linking_signal(definition) is False


def test_true_for_bare_leaf_expression() -> None:
    definition = _signal({"field": "linked_workitem_keys", "operator": "is_empty"})
    assert is_source_linking_signal(definition) is True


def test_false_for_any_with_emptiness_or_other() -> None:
    definition = _signal(
        {
            "type": "group",
            "operator": "any",
            "conditions": [
                {"field": "linked_workitem_keys", "operator": "is_empty"},
                {"field": "pipeline_status", "operator": "is", "value": "failed"},
            ],
        }
    )
    assert is_source_linking_signal(definition) is False


def test_true_for_any_with_only_emptiness() -> None:
    definition = _signal(
        {
            "type": "group",
            "operator": "any",
            "conditions": [
                {"field": "linked_workitem_keys", "operator": "is_empty"},
                {"field": "linked_workitem_keys", "operator": "is_empty"},
            ],
        }
    )
    assert is_source_linking_signal(definition) is True


def test_false_when_emptiness_only_inside_nested_any() -> None:
    definition = _signal(
        {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "state", "operator": "is", "value": "open"},
                {
                    "type": "group",
                    "operator": "any",
                    "conditions": [
                        {"field": "linked_workitem_keys", "operator": "is_empty"},
                        {"field": "pipeline_status", "operator": "is", "value": "failed"},
                    ],
                },
            ],
        }
    )
    assert is_source_linking_signal(definition) is False


def test_true_when_top_level_conjunct_guarantees_emptiness() -> None:
    definition = _signal(
        {
            "type": "group",
            "operator": "all",
            "conditions": [
                {"field": "linked_workitem_keys", "operator": "is_empty"},
                {
                    "type": "group",
                    "operator": "any",
                    "conditions": [
                        {"field": "state", "operator": "is", "value": "open"},
                        {"field": "pipeline_status", "operator": "is", "value": "failed"},
                    ],
                },
            ],
        }
    )
    assert is_source_linking_signal(definition) is True
