# SPDX-License-Identifier: Apache-2.0

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import yaml

from em_radar_api.signal_config_groups import SignalConfigGroupRead
from em_radar_api.signal_definitions import SignalDefinitionRead
from em_radar_config import (
    PackGroupEntry,
    PackMetadata,
    SignalEntry,
    SignalPack,
    SignalPackSpec,
)

PACK_VERSION = "0.1.0"


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


def _default_name(now: datetime) -> str:
    return f"local-overrides-{now.astimezone(UTC):%Y%m%d-%H%M%S}"


def _group_signal_entries(
    definitions: list[SignalDefinitionRead],
    *,
    export_type: str,
) -> list[SignalEntry]:
    scrub = export_type == "public_template"
    entries: list[SignalEntry] = []
    for definition in definitions:
        rules = _expression_to_rules(definition.expression, scrub=scrub)
        entries.append(
            SignalEntry(
                name=definition.name,
                description=definition.description,
                entity_type=definition.entity_type,
                rules=rules,
                report_settings=definition.report_settings,
                origin=definition.origin.value,
                template_key=definition.template_key,
            )
        )
    return entries


def _expression_to_rules(
    expression: dict[str, object],
    *,
    scrub: bool,
) -> list[dict[str, object]]:
    """Convert a grouped expression to a flat rules list with per-rule join values."""
    if expression.get("type") != "group":
        return []
    conditions = expression.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        return []
    group_operator = expression.get("operator", "all")
    join = "or" if group_operator == "any" else "and"
    rules: list[dict[str, object]] = []
    for i, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            continue
        rule: dict[str, object] = {
            "field": condition.get("field"),
            "operator": condition.get("operator"),
        }
        if condition.get("operator") not in ("is_empty", "is_not_empty"):
            if not scrub:
                rule["value"] = condition.get("value")
        if i < len(conditions) - 1 and len(conditions) > 1:
            rule["join"] = join
        rules.append(rule)
    return rules


def _slugify(text: str) -> str | None:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if re.fullmatch(r"[a-z][a-z0-9-]{1,62}[a-z0-9]", slug):
        return slug
    return None
