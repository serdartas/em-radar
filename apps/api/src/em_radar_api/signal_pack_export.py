import re
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import yaml

from em_radar_api.signal_config_groups import SignalConfigGroupRead
from em_radar_api.signal_configs import SignalConfigRead
from em_radar_api.signal_definitions import SignalDefinitionRead
from em_radar_config import (
    SIGNAL_CATALOG,
    FieldMappings,
    PackGroupEntry,
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


def export_signal_groups_pack(
    groups: list[SignalConfigGroupRead],
    definitions_by_id: Mapping[UUID, SignalDefinitionRead],
    *,
    export_type: str,
    name: str | None = None,
    now: datetime | None = None,
) -> str:
    ordered_definitions: list[SignalDefinitionRead] = []
    seen_ids: set[UUID] = set()
    for group in groups:
        for signal_id in group.signal_ids:
            definition = definitions_by_id.get(signal_id)
            if definition is not None and signal_id not in seen_ids:
                seen_ids.add(signal_id)
                ordered_definitions.append(definition)

    group_entries = [
        PackGroupEntry(
            name=group.name,
            description=group.description,
            signals=[
                definitions_by_id[signal_id].name
                for signal_id in group.signal_ids
                if signal_id in definitions_by_id
            ],
        )
        for group in groups
    ]

    default_name = (_slugify(groups[0].name) if len(groups) == 1 else None) or _default_name(
        now or datetime.now(UTC)
    )
    description = (
        f"Signal config group: {groups[0].name}"
        if len(groups) == 1
        else f"Signal config groups: {', '.join(group.name for group in groups)}"
    )
    pack = SignalPack(
        apiVersion="emradar.dev/v1",
        kind="SignalPack",
        metadata=PackMetadata(
            name=name or default_name,
            version=PACK_VERSION,
            description=description,
        ),
        spec=SignalPackSpec(
            export_type=export_type,
            signals=_group_signal_entries(ordered_definitions, export_type=export_type),
            groups=group_entries,
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


def _group_signal_entries(
    definitions: list[SignalDefinitionRead],
    *,
    export_type: str,
) -> list[SignalEntry]:
    scrub = export_type == "public_template"
    return [
        SignalEntry(
            name=definition.name,
            description=definition.description,
            entity_type=definition.entity_type,
            expression=_scrub_expression(definition.expression) if scrub else definition.expression,
            report_settings=definition.report_settings,
            enabled=definition.enabled,
            origin=definition.origin.value,
            template_key=definition.template_key,
        )
        for definition in definitions
    ]


def _scrub_expression(expression: dict[str, object]) -> dict[str, object]:
    """Strip org-specific condition values, keeping the field/operator structure so a
    public template documents what to configure without leaking tuned thresholds."""
    if expression.get("type") == "group":
        conditions = expression.get("conditions")
        return {
            **expression,
            "conditions": [
                _scrub_expression(condition)
                for condition in conditions
                if isinstance(condition, dict)
            ]
            if isinstance(conditions, list)
            else conditions,
        }
    return {key: value for key, value in expression.items() if key != "value"}


def _slugify(text: str) -> str | None:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if re.fullmatch(r"[a-z][a-z0-9-]{1,62}[a-z0-9]", slug):
        return slug
    return None
