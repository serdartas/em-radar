from pydantic import BaseModel, JsonValue
from sqlmodel import Session, select

from em_radar_api.models.signal_pack_history import SignalPackHistory
from em_radar_api.signal_configs import SignalConfigRead, SignalConfigTable, SignalConfigUpsert
from em_radar_config import (
    SIGNAL_CATALOG,
    PackLoadResult,
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


def preview_signal_pack_import(
    session: Session,
    raw_yaml: str,
    *,
    replace_all: bool = False,
) -> SignalPackImportPreview:
    result = load_signal_pack(raw_yaml)
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
    result = load_signal_pack(raw_yaml)
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
