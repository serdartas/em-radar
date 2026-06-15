from pathlib import Path

import pytest

from em_radar_config import (
    FieldMappings,
    JiraFieldMappings,
    PackValidationContext,
    PackValidationError,
    load_signal_pack,
)

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
    - id: blocked-without-update
      enabled: true
      params:
        days_threshold: 3
"""


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("apiVersion: emradar.dev/v1", "apiVersion: emradar.dev/v2"),
        ("kind: SignalPack", "kind: OtherPack"),
        ("name: example-pack", "name: Not_Kebab"),
        ("version: 1.2.3", "version: latest"),
        ("id: blocked-without-update", "id: unknown-signal"),
        ("days_threshold: 3", "unknown: 3"),
        ("days_threshold: 3", 'days_threshold: "3"'),
        ("enabled: true", "enabled: 1"),
        ("enabled: true", 'enabled: "false"'),
    ],
)
def test_hard_validation_rules_reject_invalid_packs(old: str, new: str) -> None:
    with pytest.raises(PackValidationError):
        load_signal_pack(VALID_PACK.replace(old, new))


def test_missing_api_version_is_rejected() -> None:
    with pytest.raises(PackValidationError):
        load_signal_pack(VALID_PACK.replace("apiVersion: emradar.dev/v1\n", ""))


def test_duplicate_mapping_keys_are_rejected() -> None:
    yaml_text = VALID_PACK.replace(
        "      enabled: true", "      enabled: true\n      enabled: false"
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

    assert result.pack.metadata.name == "default"
    assert result.warnings == ()


def test_valid_pack_returns_expected_soft_warnings() -> None:
    yaml_text = VALID_PACK.replace(
        "      enabled: true",
        """\
      enabled: true
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
        "severity-demotion",
        "unknown-scope-target",
        "unknown-scope-target",
        "advisory-field-mappings",
    ]


def test_field_mappings_are_advisory_without_current_mappings() -> None:
    yaml_text = VALID_PACK.replace(
        "spec:\n  signals:",
        """\
spec:
  field_mappings:
    jira:
      blocked_label: blocked
  signals:""",
    )

    result = load_signal_pack(yaml_text)

    assert [warning.code for warning in result.warnings] == ["advisory-field-mappings"]
