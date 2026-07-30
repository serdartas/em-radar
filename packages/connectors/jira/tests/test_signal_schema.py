from dataclasses import asdict

from em_radar_connector_jira.connector import JiraConnector


def _field(key: str) -> dict[str, object]:
    schema = asdict(JiraConnector.describe_signal_schema())
    return next(field for field in schema["fields"] if field["key"] == key)


def test_signal_schema_contains_expected_jira_issue_fields_and_operators() -> None:
    schema = asdict(JiraConnector.describe_signal_schema())

    assert schema["connector_type"] == "jira"
    assert schema["entity_types"] == ("issue",)
    assert {"project", "board", "saved_filter"} == {scope["key"] for scope in schema["scope_types"]}
    assert {"is", "is_not", "is_any_of", "is_none_of"}.issubset(set(_field("status")["operators"]))
    assert {"contains", "does_not_contain_any"}.issubset(set(_field("labels")["operators"]))
    assert {"created_at", "updated_at", "resolved_at", "age_in_current_status"}.issubset(
        {field["key"] for field in schema["fields"]}
    )
    assert "priority" not in {field["key"] for field in schema["fields"]}


def test_sprint_fields_require_sprint_capability() -> None:
    assert _field("sprint_day")["availability"]["requires_scope_capability"] == ("sprint",)
    assert _field("sprint_phase")["availability"]["requires_scope_capability"] == ("sprint",)


def test_dynamic_value_providers_reference_selected_scope() -> None:
    assert _field("status")["value_provider"] == {
        "type": "dynamic",
        "source": "jira_statuses",
        "depends_on": ("scope",),
    }
    assert _field("labels")["value_provider"]["depends_on"] == ("scope",)
