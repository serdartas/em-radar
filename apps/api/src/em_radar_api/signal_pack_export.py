from datetime import UTC, datetime

import yaml

from em_radar_api.signal_configs import SignalConfigRead
from em_radar_api.scope_definitions import ScopeDefinitionRead
from em_radar_api.signal_definitions import SignalDefinitionRead
from em_radar_api.source_connections import SourceConnectionRead
from em_radar_config import (
    SIGNAL_CATALOG,
    ConnectorReference,
    FieldMappings,
    PackMetadata,
    ScopeReference,
    SignalEntry,
    SignalPack,
    SignalPackSpec,
    SignalScope,
    TemplateEntry,
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


def export_signal_definition_pack(
    definitions: list[SignalDefinitionRead],
    scopes: list[ScopeDefinitionRead],
    connections: list[SourceConnectionRead],
    *,
    export_type: str,
    name: str | None = None,
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
            export_type=export_type,
            connectors=_connector_refs(connections) if export_type == "private_backup" else None,
            scopes=_scope_refs(scopes) if export_type == "private_backup" else None,
            signals=_definition_entries(definitions) if export_type == "private_backup" else [],
            templates=_template_entries(definitions, scopes)
            if export_type == "public_template"
            else None,
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


def _connector_refs(connections: list[SourceConnectionRead]) -> list[ConnectorReference]:
    refs: list[ConnectorReference] = []
    for connection in connections:
        config = _public_connection_config(connection.config)
        refs.append(
            ConnectorReference(
                local_ref=str(connection.id),
                connector_type=connection.connector_name.value,
                name=f"{connection.connector_name.value.title()} connection",
                base_url=str(config.get("base_url"))
                if config.get("base_url") is not None
                else None,
                auth="omitted",
            )
        )
    return refs


def _scope_refs(scopes: list[ScopeDefinitionRead]) -> list[ScopeReference]:
    return [
        ScopeReference(
            local_ref=str(scope.id),
            connector_ref=str(scope.connection_id),
            name=scope.name,
            scope_type=scope.scope_type.value,
            external_ref=scope.external_ref,
            capabilities=scope.capabilities,
        )
        for scope in scopes
    ]


def _definition_entries(definitions: list[SignalDefinitionRead]) -> list[SignalEntry]:
    return [
        SignalEntry(
            id=str(definition.id),
            name=definition.name,
            description=definition.description,
            entity_type=definition.entity_type,
            target_scopes=definition.target_scopes,
            expression=definition.expression,
            report_settings=definition.report_settings,
            enabled=definition.enabled,
            origin=definition.origin.value,
            template_key=definition.template_key,
        )
        for definition in definitions
    ]


def _template_entries(
    definitions: list[SignalDefinitionRead],
    scopes: list[ScopeDefinitionRead],
) -> list[TemplateEntry]:
    scopes_by_id = {str(scope.id): scope for scope in scopes}
    templates: list[TemplateEntry] = []
    for definition in definitions:
        capabilities = {
            capability
            for target in definition.target_scopes
            if (scope := scopes_by_id.get(target["scope_id"])) is not None
            for capability in scope.capabilities
        }
        templates.append(
            TemplateEntry(
                key=definition.template_key or str(definition.id),
                name=definition.name,
                description=definition.description,
                required_connector_type="jira",
                entity_type=definition.entity_type,
                required_scope_capabilities=sorted(capabilities),
                expression=definition.expression,
                report_settings=definition.report_settings,
                enabled_by_default=definition.enabled,
            )
        )
    return templates


def _public_connection_config(config: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in config.items()
        if key.lower() not in {"token", "password", "api_key", "secret", "authorization"}
    }
