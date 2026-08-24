from pathlib import Path

import pytest

from em_radar_config import (
    FieldMappings,
    JiraFieldMappings,
    PackValidationContext,
    PackValidationError,
    load_signal_pack,
)
from em_radar_connector_jira.connector import JiraConnector

DEFAULT_PACK_PATH = Path(__file__).parents[1] / "defaults" / "default-pack.yaml"

VALID_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: example-pack
  version: 1.2.3
  description: Example pack.
spec:
  signals:
    - name: stale-work
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: status_category
            operator: is
            value: in_progress
      report_settings:
        severity: warning
        category: flow
"""


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("apiVersion: emradar.dev/v1", "apiVersion: emradar.dev/v2"),
        ("kind: SignalPack", "kind: OtherPack"),
        ("name: example-pack", "name: Not_Kebab"),
        ("version: 1.2.3", "version: latest"),
    ],
)
def test_hard_validation_rules_reject_invalid_packs(old: str, new: str) -> None:
    with pytest.raises(PackValidationError):
        load_signal_pack(VALID_PACK.replace(old, new))


def test_missing_api_version_is_rejected() -> None:
    with pytest.raises(PackValidationError):
        load_signal_pack(VALID_PACK.replace("apiVersion: emradar.dev/v1\n", ""))


GROUP_PACK = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: group-pack
  version: 1.0.0
  description: Pack with a group.
spec:
  export_type: private_backup
  signals:
    - name: Defined signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: labels
            operator: contains
            value: x
      report_settings:
        severity: warning
        category: flow
  groups:
    - name: known-group
      signals: [Defined signal]
"""


def test_group_referencing_defined_signal_is_accepted() -> None:
    result = load_signal_pack(GROUP_PACK)

    assert result.pack.spec.groups[0].signals == ["Defined signal"]


def test_group_referencing_unknown_signal_is_rejected() -> None:
    with pytest.raises(PackValidationError, match="unknown signal"):
        load_signal_pack(GROUP_PACK.replace("signals: [Defined signal]", "signals: [Missing]"))


def test_duplicate_mapping_keys_are_rejected() -> None:
    yaml_text = VALID_PACK.replace(
        "  description: Example pack.", "  description: Example pack.\n  description: Duplicate"
    )

    with pytest.raises(PackValidationError, match="duplicate key"):
        load_signal_pack(yaml_text)


def test_minimum_em_radar_version_is_honored() -> None:
    yaml_text = VALID_PACK.replace(
        "  description: Example pack.",
        "  description: Example pack.\n  min_emradar_version: 1.0.0",
    )

    with pytest.raises(PackValidationError, match="requires EM Radar"):
        load_signal_pack(yaml_text, PackValidationContext(em_radar_version="0.9.0"))

    assert (
        load_signal_pack(
            yaml_text, PackValidationContext(em_radar_version="1.0.0")
        ).pack.metadata.name
        == "example-pack"
    )


@pytest.mark.parametrize(
    "payload",
    [
        "!!python/object/apply:os.system ['echo unsafe']",
        "${HOME}",
        "{{ env.SECRET }}",
        "https://example.com/payload",
        "eval('unsafe')",
    ],
)
def test_forbidden_content_is_rejected(payload: str) -> None:
    yaml_text = VALID_PACK.replace("Example pack.", payload)

    with pytest.raises(PackValidationError):
        load_signal_pack(yaml_text)


@pytest.mark.parametrize(
    "credential_field",
    ["token", "password", "api_key", "secret", "authorization"],
)
def test_credential_named_fields_are_rejected(credential_field: str) -> None:
    yaml_text = VALID_PACK.replace(
        "  description: Example pack.",
        f"  description: Example pack.\n  {credential_field}: unsafe",
    )

    with pytest.raises(PackValidationError, match="credential field"):
        load_signal_pack(yaml_text)


def test_recursive_alias_is_rejected() -> None:
    yaml_text = VALID_PACK.replace(
        "  description: Example pack.", "  description: &recursive [*recursive]"
    )

    with pytest.raises(PackValidationError, match="Recursive YAML aliases"):
        load_signal_pack(yaml_text)


def test_special_prefixed_field_is_rejected() -> None:
    yaml_text = VALID_PACK.replace(
        "  description: Example pack.", '  description: Example pack.\n  "!include": local'
    )

    with pytest.raises(PackValidationError, match="forbidden field name"):
        load_signal_pack(yaml_text)


def test_standard_safe_anchor_is_accepted() -> None:
    yaml_text = VALID_PACK.replace(
        "  description: Example pack.",
        "  description: &description Example pack.\n  author: *description",
    )

    result = load_signal_pack(yaml_text)

    assert result.pack.metadata.author == "Example pack."


def test_valid_default_pack_passes() -> None:
    result = load_signal_pack(DEFAULT_PACK_PATH.read_text())

    assert result.pack.metadata.name == "default-signals"
    assert result.warnings == ()


def test_valid_pack_returns_expected_soft_warnings() -> None:
    yaml_text = VALID_PACK.replace(
        "        category: flow",
        """\
        category: flow
      severity: info
      scope:
        project_keys: [MISSING]
        repository_paths: [missing/*]""",
    ).replace(
        "spec:\n  signals:",
        """\
spec:
  field_mappings:
    jira:
      story_points: customfield_10016
  signals:""",
    )
    context = PackValidationContext(
        em_radar_version="1.0.0",
        project_keys=frozenset({"KNOWN"}),
        repository_paths=frozenset({"known/repository"}),
        field_mappings=FieldMappings(jira=JiraFieldMappings(story_points="customfield_10000")),
    )

    result = load_signal_pack(yaml_text, context)

    assert [warning.code for warning in result.warnings] == [
        "unknown-scope-target",
        "unknown-scope-target",
        "advisory-field-mappings",
    ]


EXPRESSION_PACK_TEMPLATE = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: expr-pack
  version: 1.0.0
  description: Expression validation pack.
spec:
  signals:
    - name: Test signal
      entity_type: {entity_type}
      expression:
        type: group
        operator: all
        conditions:
          - field: {field}
            operator: {operator}
            value: {value}
      report_settings:
        severity: warning
        category: flow
"""

EXPRESSION_PACK_TEMPLATE_NO_VALUE = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: expr-pack
  version: 1.0.0
  description: Expression validation pack.
spec:
  signals:
    - name: Test signal
      entity_type: {entity_type}
      expression:
        type: group
        operator: all
        conditions:
          - field: {field}
            operator: {operator}
      report_settings:
        severity: warning
        category: flow
"""


def test_signal_missing_expression_raises_validation_error() -> None:
    yaml_text = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: no-expr-pack
  version: 1.0.0
  description: Pack with signal lacking expression.
spec:
  signals:
    - name: No expression signal
      entity_type: issue
      report_settings:
        severity: warning
        category: flow
"""

    with pytest.raises(PackValidationError, match="missing an expression"):
        load_signal_pack(yaml_text)


def test_valid_custom_field_condition_accepted() -> None:
    # A customfield_<n> key with a value and an allowed operator round-trips for import.
    yaml_text = EXPRESSION_PACK_TEMPLATE.format(
        entity_type="issue",
        field="customfield_10100",
        operator="is",
        value="Backend",
    )
    ctx = PackValidationContext(signal_schemas=(JiraConnector.describe_signal_schema(),))
    load_signal_pack(yaml_text, ctx)


def test_unknown_non_customfield_field_rejected() -> None:
    # sprint_scope_added_pct is a sprint-entity field, so it is unknown for the issue entity
    # type. Because it is not a customfield_<n> key it must be rejected rather than silently
    # accepted as a custom field (guards against misspelled built-in names).
    yaml_text = EXPRESSION_PACK_TEMPLATE.format(
        entity_type="issue",
        field="sprint_scope_added_pct",
        operator="greater_than",
        value=10,
    )
    ctx = PackValidationContext(signal_schemas=(JiraConnector.describe_signal_schema(),))
    with pytest.raises(PackValidationError, match="sprint_scope_added_pct"):
        load_signal_pack(yaml_text, ctx)


def test_misspelled_builtin_field_rejected() -> None:
    yaml_text = EXPRESSION_PACK_TEMPLATE.format(
        entity_type="issue",
        field="statuss",
        operator="is",
        value="Done",
    )
    ctx = PackValidationContext(signal_schemas=(JiraConnector.describe_signal_schema(),))
    with pytest.raises(PackValidationError, match="statuss"):
        load_signal_pack(yaml_text, ctx)


def test_custom_field_missing_value_rejected_for_enabled_signal() -> None:
    # An enabled (private_backup) custom-field condition with a value-taking operator must
    # supply a value, matching built-in field behaviour.
    yaml_text = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: custom-field-pack
  version: 1.0.0
  description: Custom field missing value.
spec:
  signals:
    - name: Custom field signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: customfield_10100
            operator: is
      report_settings:
        severity: warning
        category: flow
"""
    ctx = PackValidationContext(signal_schemas=(JiraConnector.describe_signal_schema(),))
    with pytest.raises(PackValidationError, match="value is required"):
        load_signal_pack(yaml_text, ctx)


def test_custom_field_missing_value_allowed_for_public_template() -> None:
    yaml_text = """\
apiVersion: emradar.dev/v1
kind: SignalPack
metadata:
  name: custom-field-template
  version: 1.0.0
  description: Custom field template.
spec:
  export_type: public_template
  signals:
    - name: Custom field signal
      entity_type: issue
      expression:
        type: group
        operator: all
        conditions:
          - field: customfield_10100
            operator: is
      report_settings:
        severity: warning
        category: flow
"""
    ctx = PackValidationContext(signal_schemas=(JiraConnector.describe_signal_schema(),))
    load_signal_pack(yaml_text, ctx)


def test_custom_field_is_empty_operator_needs_no_value() -> None:
    yaml_text = EXPRESSION_PACK_TEMPLATE_NO_VALUE.format(
        entity_type="issue",
        field="customfield_10100",
        operator="is_empty",
    )
    ctx = PackValidationContext(signal_schemas=(JiraConnector.describe_signal_schema(),))
    load_signal_pack(yaml_text, ctx)


def test_unknown_field_with_disallowed_operator_rejected() -> None:
    # An operator not in the custom-field allowlist (is_before) must still be rejected.
    yaml_text = EXPRESSION_PACK_TEMPLATE.format(
        entity_type="issue",
        field="jira_private_priority",
        operator="is_before",
        value="some-value",
    )
    ctx = PackValidationContext(signal_schemas=(JiraConnector.describe_signal_schema(),))

    with pytest.raises(PackValidationError, match="jira_private_priority"):
        load_signal_pack(yaml_text, ctx)


def test_field_mappings_are_advisory_without_current_mappings() -> None:
    yaml_text = VALID_PACK.replace(
        "spec:\n  signals:",
        """\
spec:
  field_mappings:
    jira:
      story_points: customfield_99999
  signals:""",
    )

    result = load_signal_pack(yaml_text)

    assert [warning.code for warning in result.warnings] == ["advisory-field-mappings"]


def test_empty_signals_is_rejected() -> None:
    yaml_text = VALID_PACK.split("  signals:")[0] + "  signals: []\n"
    with pytest.raises(PackValidationError, match="spec.signals is missing or empty"):
        load_signal_pack(yaml_text)


def test_missing_signals_is_rejected() -> None:
    yaml_text = VALID_PACK.split("  signals:")[0] + "  export_type: private_backup\n"
    with pytest.raises(PackValidationError, match="spec.signals is missing or empty"):
        load_signal_pack(yaml_text)


def test_signal_without_name_is_rejected() -> None:
    yaml_text = VALID_PACK.replace("    - name: stale-work\n", "    - description: nameless\n")
    with pytest.raises(PackValidationError, match="missing a name"):
        load_signal_pack(yaml_text)
