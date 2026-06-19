from pydantic import BaseModel, JsonValue
from sqlmodel import Session, select

from em_radar_api.models.signal_pack_history import SignalPackHistory
from em_radar_api.repositories.signal_definitions import create_signal_definition
from em_radar_api.scope_definitions import ScopeDefinitionTable
from em_radar_api.signal_definitions import SignalDefinitionCreate
from em_radar_api.signal_configs import SignalConfigRead, SignalConfigTable, SignalConfigUpsert
from em_radar_api.tables import ProjectTable, RepositoryTable
from em_radar_config import (
    SIGNAL_CATALOG,
    PackLoadResult,
    PackValidationContext,
    PackValidationWarning,
    SignalEntry,
    SignalPack,
    load_signal_pack,
)
from em_radar_core.models import Severity


class BoolChange(BaseModel):
    before: bool
    after: bool


class SeverityChange(BaseModel):
    before: Severity
    after: Severity


class ParamsChange(BaseModel):
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]


class SignalImportDiff(BaseModel):
    signal_id: str
    enabled: BoolChange | None = None
    severity: SeverityChange | None = None
    params: ParamsChange | None = None


class ImportWarning(BaseModel):
    code: str
    message: str
    path: str


class SignalPackImportPreview(BaseModel):
    pack_name: str
    warnings: list[ImportWarning]
    changes: list[SignalImportDiff]
    unresolved_mappings: list[str] = []
    imported_signal_names: list[str] = []


def preview_signal_pack_import(
    session: Session,
    raw_yaml: str,
    *,
    replace_all: bool = False,
) -> SignalPackImportPreview:
    result = load_signal_pack(raw_yaml, _validation_context(session))
    if _is_definition_pack(result.pack):
        return _preview_definition_pack(session, result)
    configs = {
        config.signal_id: config
        for config in session.exec(select(SignalConfigTable).order_by(SignalConfigTable.signal_id))
    }
    return _preview(result, configs, replace_all=replace_all)


def apply_signal_pack_import(
    session: Session,
    raw_yaml: str,
    *,
    replace_all: bool = False,
) -> SignalPackImportPreview:
    result = load_signal_pack(raw_yaml, _validation_context(session))
    if _is_definition_pack(result.pack):
        preview = _preview_definition_pack(session, result)
        for signal in result.pack.spec.signals:
            create_signal_definition(session, _definition_from_signal(signal, session, result.pack))
        for template in result.pack.spec.templates or []:
            create_signal_definition(
                session,
                SignalDefinitionCreate(
                    name=template.name,
                    description=template.description,
                    entity_type=template.entity_type,
                    target_scopes=[],
                    expression=template.expression,
                    report_settings=template.report_settings,
                    enabled=False,
                    origin="imported",
                    template_key=template.key,
                ),
            )
        session.add(SignalPackHistory(pack_name=result.pack.metadata.name, raw_yaml=raw_yaml))
        session.commit()
        return preview
    rows = {
        row.signal_id: row
        for row in session.exec(select(SignalConfigTable).order_by(SignalConfigTable.signal_id))
    }
    preview = _preview(result, rows, replace_all=replace_all)

    if replace_all:
        for signal_id in SIGNAL_CATALOG:
            _write_config(rows, _default_config(signal_id))

    for signal in result.pack.spec.signals:
        _write_config(rows, _config_from_signal(result.pack, signal))

    session.add_all(rows.values())
    session.add(SignalPackHistory(pack_name=result.pack.metadata.name, raw_yaml=raw_yaml))
    session.commit()
    return preview


def _preview(
    result: PackLoadResult,
    configs: dict[str, SignalConfigRead | SignalConfigTable],
    *,
    replace_all: bool,
) -> SignalPackImportPreview:
    desired = (
        {signal_id: _default_config(signal_id) for signal_id in SIGNAL_CATALOG}
        if replace_all
        else {}
    )
    desired.update(
        {signal.id: _config_from_signal(result.pack, signal) for signal in result.pack.spec.signals}
    )
    return SignalPackImportPreview(
        pack_name=result.pack.metadata.name,
        warnings=[_import_warning(warning) for warning in result.warnings],
        changes=[
            change
            for signal_id, target in desired.items()
            if (change := _signal_diff(signal_id, target, configs.get(signal_id))) is not None
        ],
    )


def _signal_diff(
    signal_id: str,
    after: SignalConfigUpsert,
    current: SignalConfigRead | SignalConfigTable | None,
) -> SignalImportDiff | None:
    before = _effective_config(signal_id, current)
    enabled = (
        BoolChange(before=before.enabled, after=after.enabled)
        if before.enabled != after.enabled
        else None
    )
    before_severity = before.severity_override or SIGNAL_CATALOG[signal_id].default_severity
    after_severity = after.severity_override or SIGNAL_CATALOG[signal_id].default_severity
    severity = (
        SeverityChange(before=before_severity, after=after_severity)
        if before_severity != after_severity
        else None
    )
    params = (
        ParamsChange(before=before.params, after=after.params)
        if before.params != after.params
        else None
    )
    if enabled is None and severity is None and params is None:
        return None
    return SignalImportDiff(
        signal_id=signal_id,
        enabled=enabled,
        severity=severity,
        params=params,
    )


def _config_from_signal(pack: SignalPack, signal: SignalEntry) -> SignalConfigUpsert:
    catalog_entry = SIGNAL_CATALOG[signal.id]
    defaults = pack.spec.defaults
    scope = signal.scope or (defaults.scope if defaults is not None else None)
    return SignalConfigUpsert(
        signal_id=signal.id,
        enabled=signal.enabled,
        severity_override=signal.severity
        or (defaults.severity_override if defaults is not None else None),
        params=catalog_entry.params_schema.model_validate(signal.params or {}).model_dump(
            mode="json"
        ),
        scope=scope.model_dump(mode="json", exclude_none=True) if scope is not None else {},
    )


def _effective_config(
    signal_id: str,
    current: SignalConfigRead | SignalConfigTable | None,
) -> SignalConfigUpsert:
    if current is not None:
        return SignalConfigUpsert.model_validate(current)
    return _default_config(signal_id)


def _default_config(signal_id: str) -> SignalConfigUpsert:
    return SignalConfigUpsert(
        signal_id=signal_id,
        params=SIGNAL_CATALOG[signal_id].params_schema().model_dump(mode="json"),
    )


def _write_config(rows: dict[str, SignalConfigTable], config: SignalConfigUpsert) -> None:
    row = rows.get(config.signal_id)
    values = config.model_dump()
    if row is None:
        rows[config.signal_id] = SignalConfigTable.model_validate(values)
    else:
        row.sqlmodel_update(values)


def _import_warning(warning: PackValidationWarning) -> ImportWarning:
    return ImportWarning(code=warning.code, message=warning.message, path=warning.path)


def _is_definition_pack(pack: SignalPack) -> bool:
    return pack.spec.export_type in {"private_backup", "public_template"} and (
        bool(pack.spec.templates)
        or any(signal.expression is not None for signal in pack.spec.signals)
    )


def _preview_definition_pack(session: Session, result: PackLoadResult) -> SignalPackImportPreview:
    scope_mapping = _scope_mapping(session, result.pack)
    unresolved = [
        template.key for template in result.pack.spec.templates or [] if template.enabled_by_default
    ]
    unresolved.extend(
        signal.name or signal.id or "unnamed signal"
        for signal in result.pack.spec.signals
        if signal.enabled and _has_unresolved_scope(signal, scope_mapping)
    )
    return SignalPackImportPreview(
        pack_name=result.pack.metadata.name,
        warnings=[_import_warning(warning) for warning in result.warnings],
        changes=[],
        unresolved_mappings=unresolved,
        imported_signal_names=[
            *(template.name for template in result.pack.spec.templates or []),
            *(signal.name or signal.id or "unnamed signal" for signal in result.pack.spec.signals),
        ],
    )


def _definition_from_signal(
    signal: SignalEntry,
    session: Session,
    pack: SignalPack,
) -> SignalDefinitionCreate:
    scope_mapping = _scope_mapping(session, pack)
    target_scopes = _mapped_target_scopes(signal, scope_mapping)
    return SignalDefinitionCreate(
        name=signal.name or signal.id or "Imported signal",
        description=signal.description,
        entity_type=signal.entity_type or "issue",
        target_scopes=target_scopes,
        expression=signal.expression or {"type": "group", "operator": "all", "conditions": []},
        report_settings=signal.report_settings or {"severity": "warning", "category": "imported"},
        enabled=signal.enabled
        and bool(target_scopes)
        and not _has_unresolved_scope(signal, scope_mapping),
        origin=signal.origin or "imported",
        template_key=signal.template_key,
    )


def _scope_mapping(session: Session, pack: SignalPack) -> dict[str, dict[str, str]]:
    local_scopes = session.exec(select(ScopeDefinitionTable)).all()
    mapping: dict[str, dict[str, str]] = {}
    exported_scopes = pack.spec.scopes or []
    for exported in exported_scopes:
        local = _matching_scope(
            local_scopes, exported.scope_type, exported.external_ref, exported.name
        )
        if local is not None:
            mapping[exported.local_ref] = {
                "connector_id": str(local.connection_id),
                "scope_id": str(local.id),
                "scope_type": local.scope_type.value,
            }
    for local in local_scopes:
        mapping.setdefault(
            str(local.id),
            {
                "connector_id": str(local.connection_id),
                "scope_id": str(local.id),
                "scope_type": local.scope_type.value,
            },
        )
    return mapping


def _matching_scope(
    local_scopes: list[ScopeDefinitionTable],
    scope_type: str,
    external_ref: dict[str, JsonValue],
    name: str,
) -> ScopeDefinitionTable | None:
    for local in local_scopes:
        if local.scope_type.value != scope_type:
            continue
        if _external_ref_matches(local.external_ref, external_ref):
            return local
    return next(
        (
            local
            for local in local_scopes
            if local.scope_type.value == scope_type and local.name == name
        ),
        None,
    )


def _external_ref_matches(
    local_ref: dict[str, object],
    exported_ref: dict[str, JsonValue],
) -> bool:
    comparable_keys = {"type", "id", "key", "name"}
    exported_values = {
        key: exported_ref.get(key) for key in comparable_keys if exported_ref.get(key) is not None
    }
    if not exported_values:
        return False
    return all(local_ref.get(key) == value for key, value in exported_values.items())


def _mapped_target_scopes(
    signal: SignalEntry,
    scope_mapping: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    return [
        scope_mapping[scope_ref]
        for target in signal.target_scopes or []
        if (scope_ref := target.get("scope_id") or target.get("scope_ref")) in scope_mapping
    ]


def _has_unresolved_scope(
    signal: SignalEntry,
    scope_mapping: dict[str, dict[str, str]],
) -> bool:
    target_scopes = signal.target_scopes or []
    if not target_scopes:
        return True
    return len(_mapped_target_scopes(signal, scope_mapping)) != len(target_scopes)


def _validation_context(session: Session) -> PackValidationContext:
    return PackValidationContext(
        project_keys=frozenset(session.exec(select(ProjectTable.key))),
        repository_paths=frozenset(session.exec(select(RepositoryTable.full_path))),
    )
