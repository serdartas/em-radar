from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
import re

from pydantic import ValidationError
import yaml
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent, CollectionStartEvent, ScalarEvent
from yaml.nodes import MappingNode

from em_radar_config.catalog import SIGNAL_CATALOG
from em_radar_config.models import FieldMappings, SignalPack, SignalScope
from em_radar_core.connectors import SignalCapabilitySchema, SignalField
from em_radar_core.models import Severity

API_VERSION = "emradar.dev/v1"
PACK_KIND = "SignalPack"
EM_RADAR_VERSION = "0.0.0"

_CREDENTIAL_FIELDS = {"token", "password", "api_key", "secret", "authorization"}
_EXECUTABLE_FIELDS = {"code", "command", "script"}
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_TEMPLATE_PATTERN = re.compile(r"\$\{[^}]+\}|\{\{.*?\}\}|<%.*?%>")
_EXECUTABLE_PATTERN = re.compile(r"^(?:#!|javascript:)|\b(?:eval|exec)\s*\(", re.IGNORECASE)
_REMOTE_URL_PATTERN = re.compile(r"^(?:https?|ftp)://", re.IGNORECASE)
_MAX_ALIASES = 20


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=False)
            if not isinstance(key, Hashable):
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found an unhashable mapping key",
                    key_node.start_mark,
                )
            if key in seen:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


class PackValidationError(ValueError):
    """Raised when a signal pack violates a hard validation rule."""


@dataclass(frozen=True)
class PackValidationWarning:
    code: str
    message: str
    path: str


@dataclass(frozen=True)
class PackValidationContext:
    em_radar_version: str = EM_RADAR_VERSION
    project_keys: frozenset[str] | None = None
    repository_paths: frozenset[str] | None = None
    field_mappings: FieldMappings | None = None
    signal_schemas: tuple[SignalCapabilitySchema, ...] = ()


@dataclass(frozen=True)
class PackLoadResult:
    pack: SignalPack
    warnings: tuple[PackValidationWarning, ...] = field(default_factory=tuple)


def load_signal_pack(
    yaml_text: str, context: PackValidationContext | None = None
) -> PackLoadResult:
    """Safely parse and validate a signal pack."""
    validation_context = context or PackValidationContext()
    raw_pack = _safe_load(yaml_text)
    _check_forbidden_content(raw_pack)

    try:
        pack = SignalPack.model_validate(raw_pack)
    except ValidationError as exc:
        raise PackValidationError(f"Invalid signal pack structure: {exc}") from exc

    _validate_pack(pack, validation_context)
    return PackLoadResult(pack=pack, warnings=tuple(_collect_warnings(pack, validation_context)))


def _safe_load(yaml_text: str) -> object:
    aliases = 0
    anchors = 0
    try:
        for event in yaml.parse(yaml_text, Loader=yaml.SafeLoader):
            if isinstance(event, AliasEvent):
                aliases += 1
                if aliases > _MAX_ALIASES:
                    raise PackValidationError("YAML contains too many aliases")
            if isinstance(event, (CollectionStartEvent, ScalarEvent)):
                if event.anchor is not None:
                    anchors += 1
                    if anchors > _MAX_ALIASES:
                        raise PackValidationError("YAML contains too many anchors")
                if event.tag is not None and not event.tag.startswith("tag:yaml.org,2002:"):
                    raise PackValidationError("YAML tagged constructors are forbidden")
        value = yaml.load(yaml_text, Loader=_UniqueKeySafeLoader)
    except PackValidationError:
        raise
    except yaml.YAMLError as exc:
        raise PackValidationError(f"Invalid or unsafe YAML: {exc}") from exc

    if not isinstance(value, Mapping):
        raise PackValidationError("Signal pack YAML must contain a top-level mapping")
    _reject_recursive_aliases(value, set(), set())
    return value


def _reject_recursive_aliases(value: object, active: set[int], visited: set[int]) -> None:
    if not isinstance(value, (Mapping, list)):
        return
    identity = id(value)
    if identity in active:
        raise PackValidationError("Recursive YAML aliases are forbidden")
    if identity in visited:
        return
    active.add(identity)
    children = value.values() if isinstance(value, Mapping) else value
    for child in children:
        _reject_recursive_aliases(child, active, visited)
    active.remove(identity)
    visited.add(identity)


def _check_forbidden_content(value: object, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise PackValidationError(f"{_format_path(path)} contains a non-string field name")
            normalized_key = key.casefold()
            child_path = (*path, key)
            if normalized_key in _CREDENTIAL_FIELDS:
                raise PackValidationError(f"{_format_path(child_path)} is a credential field")
            if normalized_key in _EXECUTABLE_FIELDS:
                raise PackValidationError(f"{_format_path(child_path)} is executable content")
            if key.startswith(("!", "&", "*", "<<")):
                raise PackValidationError(f"{_format_path(child_path)} has a forbidden field name")
            _check_forbidden_content(child, child_path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _check_forbidden_content(child, (*path, str(index)))
        return
    if isinstance(value, str):
        if _TEMPLATE_PATTERN.search(value):
            raise PackValidationError(f"{_format_path(path)} contains template expansion")
        if _EXECUTABLE_PATTERN.search(value):
            raise PackValidationError(f"{_format_path(path)} contains executable content")
        if path != ("metadata", "homepage") and _REMOTE_URL_PATTERN.match(value):
            raise PackValidationError(f"{_format_path(path)} contains a remote URL")


def _validate_pack(pack: SignalPack, context: PackValidationContext) -> None:
    if pack.api_version != API_VERSION:
        raise PackValidationError(f"apiVersion must be {API_VERSION}")
    if pack.kind != PACK_KIND:
        raise PackValidationError(f"kind must be {PACK_KIND}")
    if not _NAME_PATTERN.fullmatch(pack.metadata.name):
        raise PackValidationError("metadata.name must be lowercase kebab-case")
    _parse_semver(pack.metadata.version, "metadata.version")
    if pack.metadata.min_emradar_version is not None:
        minimum = _parse_semver(pack.metadata.min_emradar_version, "metadata.min_emradar_version")
        running = _parse_semver(context.em_radar_version, "running EM Radar version")
        if _compare_semver(minimum, running) > 0:
            raise PackValidationError(
                f"Pack requires EM Radar {pack.metadata.min_emradar_version} or newer"
            )

    if pack.spec.export_type not in {"private_backup", "public_template"}:
        raise PackValidationError("spec.export_type must be private_backup or public_template")
    for index, signal in enumerate(pack.spec.signals):
        if signal.id is not None and signal.id in SIGNAL_CATALOG:
            catalog_entry = SIGNAL_CATALOG[signal.id]
            try:
                catalog_entry.params_schema.model_validate(signal.params or {})
            except ValidationError as exc:
                raise PackValidationError(f"Invalid params for signal {signal.id}: {exc}") from exc
        elif signal.expression is None:
            raise PackValidationError(f"spec.signals.{index}.expression is required")
        if signal.expression is not None:
            _validate_signal_expression(
                signal.expression,
                signal.entity_type or "issue",
                context.signal_schemas,
                path=f"spec.signals.{index}.expression",
                allow_missing_values=not signal.enabled,
            )

    signal_names = {signal.name for signal in pack.spec.signals if signal.name is not None}
    for group_index, group in enumerate(pack.spec.groups):
        for signal_name in group.signals:
            if signal_name not in signal_names:
                raise PackValidationError(
                    f"spec.groups.{group_index} references unknown signal {signal_name!r}"
                )


def _validate_signal_expression(
    expression: Mapping[str, object],
    entity_type: str,
    schemas: tuple[SignalCapabilitySchema, ...],
    *,
    path: str,
    allow_missing_values: bool,
    depth: int = 0,
) -> None:
    if not schemas:
        return
    schema = next((schema for schema in schemas if entity_type in schema.entity_types), None)
    if schema is None:
        raise PackValidationError(f"{path} uses unsupported entity_type {entity_type!r}")
    _validate_expression_node(
        expression,
        {field.key: field for field in schema.fields},
        path=path,
        allow_missing_values=allow_missing_values,
        depth=depth,
    )


def _validate_expression_node(
    expression: Mapping[str, object],
    fields: Mapping[str, SignalField],
    *,
    path: str,
    allow_missing_values: bool,
    depth: int,
) -> None:
    if expression.get("type") == "group":
        if depth > 1:
            raise PackValidationError(f"{path} supports only one nested group")
        if expression.get("operator") not in {"all", "any"}:
            raise PackValidationError(f"{path}.operator must be all or any")
        conditions = expression.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise PackValidationError(f"{path}.conditions requires at least one condition")
        for index, condition in enumerate(conditions):
            if not isinstance(condition, Mapping):
                raise PackValidationError(f"{path}.conditions.{index} must be an object")
            _validate_expression_node(
                condition,
                fields,
                path=f"{path}.conditions.{index}",
                allow_missing_values=allow_missing_values,
                depth=depth + 1,
            )
        return

    field_key = expression.get("field")
    operator = expression.get("operator")
    if not isinstance(field_key, str) or not isinstance(operator, str):
        raise PackValidationError(f"{path} requires field and operator")
    field_schema = fields.get(field_key)
    if field_schema is None:
        raise PackValidationError(f"{path}.field {field_key!r} is not supported")
    if operator not in field_schema.operators:
        raise PackValidationError(f"{path}.operator {operator!r} is not valid for {field_key!r}")
    if operator in {"is_empty", "is_not_empty"}:
        return
    if "value" not in expression:
        if allow_missing_values:
            return
        raise PackValidationError(f"{path}.value is required for enabled signals")
    _validate_condition_value(expression["value"], field_schema, operator, path)


def _validate_condition_value(
    value: object, field_schema: SignalField, operator: str, path: str
) -> None:
    if operator in {"is_any_of", "is_none_of", "contains_any", "does_not_contain_any"}:
        if not isinstance(value, list) or not value:
            raise PackValidationError(f"{path}.value must be a non-empty list")
        return
    if operator == "between":
        if isinstance(value, list):
            if len(value) != 2:
                raise PackValidationError(f"{path}.value must contain exactly two values")
            return
        if isinstance(value, Mapping):
            required_keys = {"start", "end"} if field_schema.type == "date" else {"min", "max"}
            if not required_keys.issubset(value):
                raise PackValidationError(
                    f"{path}.value must contain {'/'.join(sorted(required_keys))}"
                )
            return
        raise PackValidationError(f"{path}.value must be a range")
    if field_schema.type in {"number", "sprint_relative_day"} and not isinstance(
        value, (int, float)
    ):
        raise PackValidationError(f"{path}.value must be numeric")
    if field_schema.type == "duration":
        if isinstance(value, (int, float)):
            return
        if isinstance(value, Mapping) and isinstance(value.get("amount"), (int, float)):
            unit = value.get("unit", "days")
            if unit in {"hours", "days"}:
                return
        raise PackValidationError(f"{path}.value must be a duration")


def _parse_semver(version: str, field_name: str) -> tuple[int, int, int, tuple[str, ...] | None]:
    match = _SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise PackValidationError(f"{field_name} must be a valid semantic version")
    prerelease = tuple(match.group(4).split(".")) if match.group(4) is not None else None
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease


def _compare_semver(
    left: tuple[int, int, int, tuple[str, ...] | None],
    right: tuple[int, int, int, tuple[str, ...] | None],
) -> int:
    if left[:3] != right[:3]:
        return 1 if left[:3] > right[:3] else -1
    left_pre, right_pre = left[3], right[3]
    if left_pre == right_pre:
        return 0
    if left_pre is None:
        return 1
    if right_pre is None:
        return -1
    for left_part, right_part in zip(left_pre, right_pre, strict=False):
        if left_part == right_part:
            continue
        if left_part.isdigit() and right_part.isdigit():
            return 1 if int(left_part) > int(right_part) else -1
        if left_part.isdigit() != right_part.isdigit():
            return -1 if left_part.isdigit() else 1
        return 1 if left_part > right_part else -1
    return (len(left_pre) > len(right_pre)) - (len(left_pre) < len(right_pre))


def _collect_warnings(
    pack: SignalPack, context: PackValidationContext
) -> Sequence[PackValidationWarning]:
    warnings: list[PackValidationWarning] = []
    severity_rank = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}
    defaults = pack.spec.defaults
    if defaults is not None:
        warnings.extend(_scope_warnings(defaults.scope, context, "spec.defaults.scope"))
    for index, signal in enumerate(pack.spec.signals):
        if signal.id is None or signal.id not in SIGNAL_CATALOG:
            continue
        catalog_entry = SIGNAL_CATALOG[signal.id]
        effective_severity = signal.severity or (defaults.severity_override if defaults else None)
        if (
            effective_severity is not None
            and severity_rank[catalog_entry.default_severity] - severity_rank[effective_severity]
            >= 2
        ):
            severity_path = (
                f"spec.signals.{index}.severity"
                if signal.severity is not None
                else "spec.defaults.severity_override"
            )
            warnings.append(
                PackValidationWarning(
                    code="severity-demotion",
                    message=(
                        f"{signal.id} is demoted from {catalog_entry.default_severity.value} "
                        f"to {effective_severity.value}"
                    ),
                    path=severity_path,
                )
            )
        warnings.extend(_scope_warnings(signal.scope, context, f"spec.signals.{index}.scope"))

    if pack.spec.field_mappings is not None and pack.spec.field_mappings != context.field_mappings:
        warnings.append(
            PackValidationWarning(
                code="advisory-field-mappings",
                message="Field mappings are advisory and differ from the current mappings",
                path="spec.field_mappings",
            )
        )
    return warnings


def _scope_warnings(
    scope: SignalScope | None, context: PackValidationContext, path: str
) -> list[PackValidationWarning]:
    warnings: list[PackValidationWarning] = []
    if scope is None:
        return warnings
    if context.project_keys is not None:
        for project_key in scope.project_keys or []:
            if project_key not in context.project_keys:
                warnings.append(
                    PackValidationWarning(
                        code="unknown-scope-target",
                        message=f"Project key {project_key} does not exist",
                        path=f"{path}.project_keys",
                    )
                )
    if context.repository_paths is not None:
        for repository_path in scope.repository_paths or []:
            if not any(
                fnmatch(candidate, repository_path) for candidate in context.repository_paths
            ):
                warnings.append(
                    PackValidationWarning(
                        code="unknown-scope-target",
                        message=f"Repository path {repository_path} does not exist",
                        path=f"{path}.repository_paths",
                    )
                )
    return warnings


def _format_path(path: tuple[str, ...]) -> str:
    return ".".join(path) or "document"
