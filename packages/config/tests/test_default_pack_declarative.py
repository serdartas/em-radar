"""Verification tests for M5-13: declarative default pack and unified seeding.

Asserts that:
1. default-pack.yaml validates against the signal-pack schema.
2. Every signal entry is fully declarative (has an expression, no bare id+params).
3. The pack contains exactly the 8 expected work-item signals.
4. A fresh-DB seed produces the default group with 8 enabled SignalDefinitions.
5. The seeded group exports back to equivalent YAML (round-trip).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, select

from em_radar_config import load_signal_pack

DEFAULT_PACK_PATH = Path(__file__).parents[1] / "defaults" / "default-pack.yaml"

EXPECTED_TEMPLATE_KEYS = {
    "stale-in-progress-work-item",
    "blocked-without-update",
    "story-without-acceptance-criteria",
    "story-without-parent-epic",
    "epic-too-broad",
    "epic-without-measurable-description",
    "repeated-carry-over",
    "sprint-scope-churn",
}


# ---------------------------------------------------------------------------
# Pack schema and content assertions (no database required)
# ---------------------------------------------------------------------------


def test_default_pack_validates_against_schema() -> None:
    """Validates expressions against the live Jira connector capability schema."""
    from em_radar_config import PackValidationContext
    from em_radar_connector_jira.connector import JiraConnector

    ctx = PackValidationContext(signal_schemas=(JiraConnector.describe_signal_schema(),))
    result = load_signal_pack(DEFAULT_PACK_PATH.read_text(encoding="utf-8"), ctx)

    assert result.pack.api_version == "emradar.dev/v1"
    assert result.pack.kind == "SignalPack"
    assert result.warnings == ()


def test_all_signals_are_fully_declarative() -> None:
    """Every signal must have an expression — no bare id+params old-format entries."""
    pack = load_signal_pack(DEFAULT_PACK_PATH.read_text()).pack

    for signal in pack.spec.signals:
        assert signal.expression is not None, f"Signal {signal.name!r} is missing an expression"
        assert signal.entity_type is not None
        assert signal.report_settings is not None


def test_pack_contains_exactly_8_work_item_signals() -> None:
    pack = load_signal_pack(DEFAULT_PACK_PATH.read_text()).pack

    assert len(pack.spec.signals) == 8
    actual_keys = {s.template_key for s in pack.spec.signals}
    assert actual_keys == EXPECTED_TEMPLATE_KEYS


def test_default_group_references_all_signals() -> None:
    pack = load_signal_pack(DEFAULT_PACK_PATH.read_text()).pack
    assert pack.spec.groups, "default-pack.yaml must define at least one group"

    default_group = next((g for g in pack.spec.groups if g.name == "Default signals"), None)
    assert default_group is not None, "pack must contain a 'Default signals' group"
    signal_names = {s.name for s in pack.spec.signals}
    for name in default_group.signals:
        assert name in signal_names, f"Group references unknown signal name: {name!r}"


def test_all_signals_are_enabled_and_system_template() -> None:
    pack = load_signal_pack(DEFAULT_PACK_PATH.read_text()).pack

    for signal in pack.spec.signals:
        assert signal.enabled is True, f"Signal {signal.name!r} must be enabled by default"
        assert signal.origin == "system_template", (
            f"Signal {signal.name!r} must have origin system_template"
        )


# ---------------------------------------------------------------------------
# Database seeding tests (requires API harness)
# ---------------------------------------------------------------------------


@pytest.fixture
def _api_harness(tmp_path) -> Iterator[SimpleNamespace]:
    import em_radar_api.tables  # noqa: F401

    from em_radar_api.db import (
        create_db_engine,
        create_session_factory,
        get_session,
        get_write_session,
    )
    from em_radar_api.main import create_app

    engine = create_db_engine(tmp_path / "m5-13-test.db")
    SQLModel.metadata.create_all(engine)
    factory = create_session_factory(engine)

    def _session():
        with factory() as session:
            yield session

    app = create_app(app_session_factory=factory)
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_write_session] = _session
    try:
        yield SimpleNamespace(client=TestClient(app), session_factory=factory)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_seed_creates_8_signal_definitions(_api_harness) -> None:
    from em_radar_api.signal_definitions import SignalDefinitionTable

    with _api_harness.client:
        pass  # triggers lifespan / seed

    with _api_harness.session_factory() as session:
        definitions = session.exec(select(SignalDefinitionTable)).all()

    assert len(definitions) == 8
    keys = {d.template_key for d in definitions}
    assert keys == EXPECTED_TEMPLATE_KEYS


def test_seed_creates_default_signals_group(_api_harness) -> None:
    from em_radar_api.signal_config_groups import SignalConfigGroupTable

    with _api_harness.client:
        pass

    with _api_harness.session_factory() as session:
        group = session.exec(
            select(SignalConfigGroupTable).where(SignalConfigGroupTable.name == "Default signals")
        ).first()

    assert group is not None
    assert len(group.signal_ids) == 8


def test_seed_is_idempotent(_api_harness) -> None:
    from em_radar_api.signal_definitions import SignalDefinitionTable

    with _api_harness.client:
        pass
    with _api_harness.client:
        pass

    with _api_harness.session_factory() as session:
        count = len(session.exec(select(SignalDefinitionTable)).all())

    assert count == 8


def test_seeded_definitions_export_to_valid_pack(_api_harness) -> None:
    """Seeded group must export back to a valid declarative SignalPack (round-trip)."""
    from em_radar_api.signal_config_groups import SignalConfigGroupTable

    with _api_harness.client:
        pass

    with _api_harness.session_factory() as session:
        group = session.exec(
            select(SignalConfigGroupTable).where(SignalConfigGroupTable.name == "Default signals")
        ).first()
        group_id = str(group.id)

    response = _api_harness.client.get(
        "/api/signal-pack/export",
        params={"group_ids": [group_id], "export_type": "private_backup"},
    )

    assert response.status_code == 200
    exported = load_signal_pack(response.text)
    assert exported.pack.api_version == "emradar.dev/v1"
    assert len(exported.pack.spec.signals) == 8
    exported_keys = {s.template_key for s in exported.pack.spec.signals}
    assert exported_keys == EXPECTED_TEMPLATE_KEYS

    # Verify expressions and report_settings survive the round-trip.
    source = load_signal_pack(DEFAULT_PACK_PATH.read_text(encoding="utf-8")).pack
    source_by_key = {s.template_key: s for s in source.spec.signals}
    for exported_signal in exported.pack.spec.signals:
        key = exported_signal.template_key
        assert exported_signal.expression == source_by_key[key].expression, (
            f"Expression mismatch for {key!r} after round-trip"
        )
        assert exported_signal.report_settings == source_by_key[key].report_settings, (
            f"report_settings mismatch for {key!r} after round-trip"
        )
