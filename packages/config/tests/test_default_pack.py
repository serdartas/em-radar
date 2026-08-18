from pathlib import Path
import tomllib

import yaml

from em_radar_config import SignalPack

DEFAULT_PACK_PATH = Path(__file__).parents[1] / "defaults" / "default-pack.yaml"
REPOSITORY_ROOT = Path(__file__).parents[3]


def test_default_pack_parses_correctly() -> None:
    pack = SignalPack.model_validate(yaml.safe_load(DEFAULT_PACK_PATH.read_text()))

    assert pack.api_version == "emradar.dev/v1"
    assert pack.kind == "SignalPack"
    assert len(pack.spec.signals) == 13
    assert all(signal.expression is not None for signal in pack.spec.signals)


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
                "signals": [
                    {
                        "name": "example-signal",
                        "expression": {
                            "type": "group",
                            "operator": "all",
                            "conditions": [
                                {
                                    "field": "status_category",
                                    "operator": "is",
                                    "value": "in_progress",
                                }
                            ],
                        },
                        "report_settings": {"severity": "warning", "category": "flow"},
                        "origin": "user_created",
                    }
                ],
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
