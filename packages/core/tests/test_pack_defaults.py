"""Tests for pack-level defaults: severity_override inherited by signals without their own severity."""

from em_radar_config import SignalPack, apply_pack_defaults


def _pack(signals: list[dict[str, object]], severity_override: str | None = None) -> SignalPack:
    spec: dict = {"signals": signals}
    if severity_override is not None:
        spec["defaults"] = {"severity_override": severity_override}
    return SignalPack.model_validate(
        {
            "apiVersion": "emradar.dev/v1",
            "kind": "SignalPack",
            "metadata": {"name": "test-pack", "version": "1.0.0", "description": "Test"},
            "spec": spec,
        }
    )


def test_severity_override_applied_when_signal_has_no_severity() -> None:
    pack = _pack(
        signals=[{"name": "No-severity signal", "enabled": True}],
        severity_override="critical",
    )

    entries = apply_pack_defaults(pack)

    assert len(entries) == 1
    assert entries[0].severity == "critical"


def test_signal_with_own_severity_keeps_it() -> None:
    pack = _pack(
        signals=[{"name": "Own-severity signal", "enabled": True, "severity": "info"}],
        severity_override="critical",
    )

    entries = apply_pack_defaults(pack)

    assert entries[0].severity == "info"


def test_mixed_signals_only_override_missing_severity() -> None:
    pack = _pack(
        signals=[
            {"name": "Has severity", "enabled": True, "severity": "warning"},
            {"name": "No severity", "enabled": True},
        ],
        severity_override="critical",
    )

    entries = apply_pack_defaults(pack)

    assert entries[0].severity == "warning"
    assert entries[1].severity == "critical"


def test_no_severity_override_on_pack_returns_entries_unchanged() -> None:
    pack = _pack(
        signals=[
            {"name": "No severity signal", "enabled": True},
        ],
    )

    entries = apply_pack_defaults(pack)

    assert entries[0].severity is None


def test_null_severity_override_on_pack_returns_entries_unchanged() -> None:
    pack = SignalPack.model_validate(
        {
            "apiVersion": "emradar.dev/v1",
            "kind": "SignalPack",
            "metadata": {"name": "test-pack", "version": "1.0.0", "description": "Test"},
            "spec": {
                "defaults": {"severity_override": None},
                "signals": [{"name": "No severity signal", "enabled": True}],
            },
        }
    )

    entries = apply_pack_defaults(pack)

    assert entries[0].severity is None


def test_apply_pack_defaults_does_not_mutate_original_entry() -> None:
    pack = _pack(
        signals=[{"name": "No severity", "enabled": True}],
        severity_override="warning",
    )
    original_entry = pack.spec.signals[0]

    entries = apply_pack_defaults(pack)

    assert original_entry.severity is None
    assert entries[0].severity == "warning"
    assert entries[0] is not original_entry
