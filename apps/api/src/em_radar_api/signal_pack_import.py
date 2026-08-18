# SPDX-License-Identifier: Apache-2.0

from typing import Literal

from pydantic import BaseModel, JsonValue
from sqlmodel import Session, select

from em_radar_api.models.signal_pack_history import SignalPackHistory
from em_radar_api.repositories.signal_config_groups import (
    create_signal_config_group,
    update_signal_config_group,
)
from em_radar_api.repositories.signal_definitions import (
    create_signal_definition,
    update_signal_definition,
)
from em_radar_api.signal_config_groups import (
    SignalConfigGroupCreate,
    SignalConfigGroupTable,
    SignalConfigGroupUpdate,
)
from em_radar_api.signal_definitions import (
    SignalDefinitionCreate,
    SignalDefinitionTable,
    SignalDefinitionUpdate,
)
from em_radar_api.tables import ProjectTable, RepositoryTable
from em_radar_connector_gitlab import GitLabConnector
from em_radar_connector_jira import JiraConnector
from em_radar_config import (
    PackGroupEntry,
    PackLoadResult,
    PackValidationContext,
    PackValidationError,
    PackValidationWarning,
    SignalEntry,
    SignalPack,
    load_signal_pack,
)

ConflictMode = Literal["skip", "overwrite", "keep_both", "cancel"]


class SeverityChange(BaseModel):
    before: str
    after: str


class ParamsChange(BaseModel):
    before: JsonValue
    after: JsonValue


class SignalImportDiff(BaseModel):
    signal_id: str
    severity: SeverityChange | None = None
    params: ParamsChange | None = None


class ImportWarning(BaseModel):
    code: str
    message: str
    path: str


class SignalPackImportPreview(BaseModel):
    pack_name: str
    warnings: list[ImportWarning] = []
    changes: list[SignalImportDiff] = []
    unresolved_mappings: list[str] = []
    imported_signal_names: list[str] = []
    signal_name_clashes: list[str] = []
    group_name_clashes: list[str] = []
    intra_pack_duplicate_signal_names: list[str] = []
    intra_pack_duplicate_group_names: list[str] = []


def preview_signal_pack_import(
    session: Session,
    raw_yaml: str,
    *,
    replace_all: bool = False,
) -> SignalPackImportPreview:
    del replace_all
    result = load_signal_pack(raw_yaml, _validation_context(session))
    return _preview_definition_pack(session, result)


def apply_signal_pack_import(
    session: Session,
    raw_yaml: str,
    *,
    replace_all: bool = False,
    conflict: ConflictMode = "keep_both",
) -> SignalPackImportPreview:
    del replace_all
    result = load_signal_pack(raw_yaml, _validation_context(session))
    preview = _preview_definition_pack(session, result)
    if conflict == "cancel":
        return preview
    duplicate_names = (
        preview.intra_pack_duplicate_signal_names + preview.intra_pack_duplicate_group_names
    )
    if duplicate_names:
        raise PackValidationError(
            "Pack contains duplicate names within a single pack: "
            + ", ".join(f"{n!r}" for n in duplicate_names)
        )
    _reject_incomplete_signals(result.pack)
    try:
        _import_definition_pack(session, result.pack, conflict)
        session.add(SignalPackHistory(pack_name=result.pack.metadata.name, raw_yaml=raw_yaml))
        session.commit()
    except ValueError as error:
        session.rollback()
        raise PackValidationError(str(error)) from error
    return preview


def _import_warning(warning: PackValidationWarning) -> ImportWarning:
    return ImportWarning(code=warning.code, message=warning.message, path=warning.path)


def _preview_definition_pack(session: Session, result: PackLoadResult) -> SignalPackImportPreview:
    pack = result.pack
    existing_signal_names = set(session.exec(select(SignalDefinitionTable.name)))
    existing_group_names = set(session.exec(select(SignalConfigGroupTable.name)))
    signal_names = [_signal_source_name(signal) for signal in pack.spec.signals]
    group_names = [group.name for group in _pack_groups(pack)]
    return SignalPackImportPreview(
        pack_name=pack.metadata.name,
        warnings=[_import_warning(warning) for warning in result.warnings],
        changes=[],
        imported_signal_names=signal_names,
        signal_name_clashes=[name for name in signal_names if name in existing_signal_names],
        group_name_clashes=[name for name in group_names if name in existing_group_names],
        intra_pack_duplicate_signal_names=_find_duplicates(signal_names),
        intra_pack_duplicate_group_names=_find_duplicates(group_names),
    )


def _import_definition_pack(session: Session, pack: SignalPack, conflict: ConflictMode) -> None:
    existing_signals = {row.name: row.id for row in session.exec(select(SignalDefinitionTable))}
    used_signal_names = set(existing_signals)
    name_to_id = {}
    for signal in pack.spec.signals:
        source_name = _signal_source_name(signal)
        definition = _definition_from_signal(signal)
        if source_name in existing_signals:
            existing_id = existing_signals[source_name]
            if conflict == "skip":
                name_to_id[source_name] = existing_id
                continue
            if conflict == "overwrite":
                update_signal_definition(
                    session,
                    existing_id,
                    SignalDefinitionUpdate(**definition.model_dump()),
                    commit=False,
                )
                name_to_id[source_name] = existing_id
                continue
            new_name = _dedupe_name(source_name, used_signal_names)
            used_signal_names.add(new_name)
            created = create_signal_definition(
                session,
                definition.model_copy(update={"name": new_name}),
                commit=False,
            )
            name_to_id[source_name] = created.id
        else:
            used_signal_names.add(source_name)
            created = create_signal_definition(session, definition, commit=False)
            name_to_id[source_name] = created.id

    existing_groups = {row.name: row.id for row in session.exec(select(SignalConfigGroupTable))}
    used_group_names = set(existing_groups)
    for group in _pack_groups(pack):
        signal_ids = [name_to_id[name] for name in group.signals if name in name_to_id]
        if group.name in existing_groups:
            if conflict == "skip":
                continue
            if conflict == "overwrite":
                update_signal_config_group(
                    session,
                    existing_groups[group.name],
                    SignalConfigGroupUpdate(description=group.description, signal_ids=signal_ids),
                    commit=False,
                )
                continue
            new_name = _dedupe_name(group.name, used_group_names)
            used_group_names.add(new_name)
            create_signal_config_group(
                session,
                SignalConfigGroupCreate(
                    name=new_name, description=group.description, signal_ids=signal_ids
                ),
                commit=False,
            )
        else:
            used_group_names.add(group.name)
            create_signal_config_group(
                session,
                SignalConfigGroupCreate(
                    name=group.name, description=group.description, signal_ids=signal_ids
                ),
                commit=False,
            )


def _pack_groups(pack: SignalPack) -> list[PackGroupEntry]:
    if pack.spec.groups:
        return pack.spec.groups
    return [
        PackGroupEntry(
            name=pack.metadata.name,
            description=pack.metadata.description,
            signals=[_signal_source_name(signal) for signal in pack.spec.signals],
        )
    ]


def _signal_source_name(signal: SignalEntry) -> str:
    return signal.name or signal.id or "Imported signal"


def _definition_from_signal(signal: SignalEntry) -> SignalDefinitionCreate:
    return SignalDefinitionCreate(
        name=_signal_source_name(signal),
        description=signal.description,
        entity_type=signal.entity_type or "issue",
        expression=_rules_to_expression(signal.rules)
        if signal.rules is not None
        else (signal.expression or {"type": "group", "operator": "all", "conditions": []}),
        report_settings=signal.report_settings or {"severity": "warning", "category": "imported"},
        origin=signal.origin or "imported",
        template_key=signal.template_key,
    )


def _rules_to_expression(rules: list[dict[str, object]]) -> dict[str, object]:
    """Convert a flat rules list back to a grouped expression."""
    if not rules:
        return {"type": "group", "operator": "all", "conditions": []}
    first_join = rules[0].get("join") if len(rules) > 1 else None
    group_operator = "any" if first_join == "or" else "all"
    conditions: list[dict[str, object]] = [
        {k: v for k, v in rule.items() if k != "join"} for rule in rules
    ]
    return {"type": "group", "operator": group_operator, "conditions": conditions}


def _reject_incomplete_signals(pack: SignalPack) -> None:
    for signal in pack.spec.signals:
        has_missing = (
            _rules_have_missing_values(signal.rules)
            if signal.rules is not None
            else (
                signal.expression is not None and _expression_has_missing_values(signal.expression)
            )
        )
        if has_missing:
            name = _signal_source_name(signal)
            raise PackValidationError(
                f"Signal {name!r} has conditions with missing values. "
                "Fill in all condition values before importing."
            )


def _rules_have_missing_values(rules: list[dict[str, object]]) -> bool:
    for rule in rules:
        operator = rule.get("operator", "")
        if operator in {"is_empty", "is_not_empty"}:
            continue
        value = rule.get("value")
        if "value" not in rule or value is None or value == "":
            return True
    return False


def _expression_has_missing_values(expression: object) -> bool:
    if not isinstance(expression, dict):
        return False
    if expression.get("type") == "group":
        return any(_expression_has_missing_values(c) for c in expression.get("conditions") or [])
    operator = expression.get("operator", "")
    if operator in {"is_empty", "is_not_empty"}:
        return False
    value = expression.get("value")
    return "value" not in expression or value is None or value == ""


def _find_duplicates(names: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in names:
        if name in seen:
            if name not in duplicates:
                duplicates.append(name)
        else:
            seen.add(name)
    return duplicates


def _dedupe_name(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    index = 2
    while f"{base} ({index})" in used:
        index += 1
    return f"{base} ({index})"


def _validation_context(session: Session) -> PackValidationContext:
    return PackValidationContext(
        project_keys=frozenset(session.exec(select(ProjectTable.key))),
        repository_paths=frozenset(session.exec(select(RepositoryTable.full_path))),
        signal_schemas=(
            JiraConnector.describe_signal_schema(),
            GitLabConnector.describe_signal_schema(),
        ),
    )
