from pathlib import Path
import tomllib

import yaml

from em_radar_config import SIGNAL_CATALOG, SignalPack

DEFAULT_PACK_PATH = Path(__file__).parents[1] / "defaults" / "default-pack.yaml"
REPOSITORY_ROOT = Path(__file__).parents[3]


def test_default_pack_parses_and_matches_catalog_defaults() -> None:
    pack = SignalPack.model_validate(yaml.safe_load(DEFAULT_PACK_PATH.read_text()))
    expected = {
        entry.id: (
            entry.default_severity,
            entry.params_schema().model_dump(mode="json"),
        )
        for entry in SIGNAL_CATALOG.values()
    }

    assert pack.api_version == "emradar.dev/v1"
    assert pack.kind == "SignalPack"
    assert len(pack.spec.signals) == 13
    assert {signal.id for signal in pack.spec.signals} == set(expected)
    assert all(signal.enabled for signal in pack.spec.signals)
    assert {signal.id: (signal.severity, signal.params) for signal in pack.spec.signals} == expected


def test_pack_models_cover_defaults_scopes_and_field_mappings() -> None:
    pack = SignalPack.model_validate(
        {
            "apiVersion": "emradar.dev/v1",
            "kind": "SignalPack",
            "metadata": {
                "name": "example-pack",
                "version": "1.0.0",
                "description": "Example",
            },
            "spec": {
                "defaults": {
                    "severity_override": "warning",
                    "scope": {"project_keys": ["RAD"]},
                },
                "signals": [{"id": "epic-too-broad", "enabled": True}],
                "field_mappings": {
                    "jira": {"story_points": "customfield_10016"},
                    "gitlab": {"workitem_key_pattern": r"[A-Z]+-\d+"},
                },
            },
        }
    )

    assert pack.spec.defaults is not None
    assert pack.spec.defaults.scope is not None
    assert pack.spec.defaults.scope.project_keys == ["RAD"]
    assert pack.spec.field_mappings is not None
    assert pack.spec.field_mappings.jira is not None
    assert pack.spec.field_mappings.jira.story_points == "customfield_10016"
    assert pack.model_dump(by_alias=True)["apiVersion"] == "emradar.dev/v1"


def test_default_pack_is_included_in_distribution_and_docker_artifacts() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())
    dockerfile = (REPOSITORY_ROOT / "deploy" / "docker" / "Dockerfile").read_text()

    assert "pyyaml" in pyproject["project"]["dependencies"]
    assert pyproject["tool"]["setuptools"]["data-files"]["packages/config/defaults"] == [
        "packages/config/defaults/default-pack.yaml"
    ]
    assert "COPY packages/config/src ./packages/config/src" in dockerfile
    assert "COPY packages/config/defaults ./packages/config/defaults" in dockerfile
