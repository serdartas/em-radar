from datetime import UTC, datetime

import yaml

from em_radar_api.signal_configs import SignalConfigRead
from em_radar_config import (
    SIGNAL_CATALOG,
    FieldMappings,
    PackMetadata,
    SignalEntry,
    SignalPack,
    SignalPackSpec,
    SignalScope,
)

PACK_VERSION = "0.1.0"
PACK_DESCRIPTION = "Exported local EM Radar signal configuration."


def export_signal_pack(
    configs: list[SignalConfigRead],
    *,
    full: bool = False,
    name: str | None = None,
    field_mappings: FieldMappings | None = None,
    now: datetime | None = None,
) -> str:
    pack = SignalPack(
        apiVersion="emradar.dev/v1",
        kind="SignalPack",
        metadata=PackMetadata(
            name=name or _default_name(now or datetime.now(UTC)),
            version=PACK_VERSION,
            description=PACK_DESCRIPTION,
        ),
        spec=SignalPackSpec(
            signals=_exported_signals(configs, full=full),
            field_mappings=field_mappings,
        ),
    )
    return yaml.safe_dump(
        pack.model_dump(mode="json", by_alias=True, exclude_none=True),
        sort_keys=False,
    )


def _exported_signals(configs: list[SignalConfigRead], *, full: bool) -> list[SignalEntry]:
    configs_by_id = {config.signal_id: config for config in configs}
    signals: list[SignalEntry] = []

    for signal_id, catalog_entry in SIGNAL_CATALOG.items():
        config = configs_by_id.get(signal_id)
        enabled = config.enabled if config is not None else True
        severity = config.severity_override if config is not None else None
        effective_severity = severity or catalog_entry.default_severity
        raw_params = config.params if config is not None else {}
        params = catalog_entry.params_schema.model_validate(raw_params).model_dump(mode="json")
        scope = (
            SignalScope.model_validate(config.scope)
            if config is not None and config.scope
            else None
        )

        touched = (
            enabled is not True
            or effective_severity != catalog_entry.default_severity
            or params != catalog_entry.params_schema().model_dump(mode="json")
            or scope is not None
        )
        if full or touched:
            signals.append(
                SignalEntry(
                    id=signal_id,
                    enabled=enabled,
                    severity=effective_severity,
                    params=params,
                    scope=scope,
                )
            )

    return signals


def _default_name(now: datetime) -> str:
    return f"local-overrides-{now.astimezone(UTC):%Y%m%d-%H%M%S}"
