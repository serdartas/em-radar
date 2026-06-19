from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeAlias

from em_radar_core.connectors import SignalCapabilitySchema, SignalField
from em_radar_core.models import (
    Confidence,
    EntityType,
    EvaluationContext,
    Severity,
    SignalDefinition,
    SignalFinding,
    SignalTargetScope,
    Sprint,
    Transition,
    WorkItem,
)
from em_radar_core.signals import SignalData

JsonObject: TypeAlias = dict[str, object]


@dataclass(frozen=True)
class ScopeDescriptor:
    connector_id: str
    scope_id: str
    scope_type: str
    name: str
    external_ref: JsonObject = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConditionMatch:
    matched: bool
    reason: str
    evidence: JsonObject


class ExpressionValidationError(ValueError):
    pass


def evaluate_signal_definition(
    definition: SignalDefinition,
    data: SignalData,
    ctx: EvaluationContext,
    schema: SignalCapabilitySchema,
    scopes: list[ScopeDescriptor],
) -> list[SignalFinding]:
    if not definition.enabled:
        return []

    scope_by_id = {scope.scope_id: scope for scope in scopes}
    target_scopes = [_scope_key(target) for target in definition.target_scopes]
    selected_scopes = [
        scope_by_id[scope_id] for scope_id in target_scopes if scope_id in scope_by_id
    ]
    if not selected_scopes:
        return []

    validate_expression(definition.expression, schema, selected_scopes)

    findings: list[SignalFinding] = []
    for scope in selected_scopes:
        for workitem in _workitems_for_scope(data, scope):
            result = _evaluate_group(definition.expression, workitem, data, ctx, scope)
            if not result.matched:
                continue
            findings.append(
                SignalFinding(
                    report_id=data.report_id,
                    signal_id=str(definition.id),
                    signal_name=definition.name,
                    severity=Severity(definition.report_settings.severity),
                    confidence=Confidence.HIGH,
                    entity_type=EntityType.WORKITEM,
                    entity_id=workitem.id,
                    title=f"{workitem.key} - {workitem.title}",
                    reason=result.reason,
                    evidence={"scope_id": scope.scope_id, **result.evidence},
                    source_link=workitem.source_url,
                    created_at=ctx.now,
                )
            )
    return findings


def preview_signal_definition(
    definition: SignalDefinition,
    data: SignalData,
    ctx: EvaluationContext,
    schema: SignalCapabilitySchema,
    scopes: list[ScopeDescriptor],
    sample_size: int = 5,
) -> JsonObject:
    warnings: list[str] = []
    try:
        findings = evaluate_signal_definition(definition, data, ctx, schema, scopes)
    except ExpressionValidationError as error:
        findings = []
        warnings.append(str(error))
    return {
        "match_count": len(findings),
        "samples": [
            {
                "item_key": finding.title.split(" - ", 1)[0],
                "title": finding.title,
                "reason": finding.reason,
                "evidence": finding.evidence,
            }
            for finding in findings[:sample_size]
        ],
        "warnings": warnings,
    }


def validate_expression(
    expression: JsonObject,
    schema: SignalCapabilitySchema,
    scopes: list[ScopeDescriptor],
    depth: int = 0,
) -> None:
    if expression.get("type") != "group":
        _validate_condition(expression, schema, scopes)
        return
    if depth > 1:
        raise ExpressionValidationError("expressions support only one nested group")
    if expression.get("operator") not in {"all", "any"}:
        raise ExpressionValidationError("group operator must be all or any")
    conditions = expression.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ExpressionValidationError("groups require at least one condition")
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ExpressionValidationError("conditions must be objects")
        validate_expression(condition, schema, scopes, depth + 1)


def _validate_condition(
    condition: JsonObject,
    schema: SignalCapabilitySchema,
    scopes: list[ScopeDescriptor],
) -> None:
    field_key = condition.get("field")
    operator = condition.get("operator")
    if not isinstance(field_key, str) or not isinstance(operator, str):
        raise ExpressionValidationError("conditions require field and operator")
    field_schema = _field_schema(schema, field_key)
    if operator not in field_schema.operators:
        raise ExpressionValidationError(f"{operator} is not valid for {field_key}")
    required = (
        field_schema.availability.requires_scope_capability
        if field_schema.availability is not None
        else ()
    )
    for scope in scopes:
        missing = set(required).difference(scope.capabilities)
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ExpressionValidationError(
                f"{field_key} requires scope capability: {missing_list}"
            )


def _evaluate_group(
    expression: JsonObject,
    workitem: WorkItem,
    data: SignalData,
    ctx: EvaluationContext,
    scope: ScopeDescriptor,
) -> ConditionMatch:
    if expression.get("type") != "group":
        return _evaluate_condition(expression, workitem, data, ctx, scope)
    conditions = [item for item in expression["conditions"] if isinstance(item, dict)]
    matches = [_evaluate_group(condition, workitem, data, ctx, scope) for condition in conditions]
    operator = expression["operator"]
    matched = (
        all(match.matched for match in matches)
        if operator == "all"
        else any(match.matched for match in matches)
    )
    active = [match for match in matches if match.matched]
    if not matched and operator == "all":
        active = [match for match in matches if not match.matched]
    return ConditionMatch(
        matched=matched,
        reason=(" and " if operator == "all" else " or ").join(match.reason for match in active),
        evidence={key: value for match in active for key, value in match.evidence.items()},
    )


def _evaluate_condition(
    condition: JsonObject,
    workitem: WorkItem,
    data: SignalData,
    ctx: EvaluationContext,
    scope: ScopeDescriptor,
) -> ConditionMatch:
    field_key = str(condition["field"])
    operator = str(condition["operator"])
    expected = condition.get("value")
    observed = _field_value(field_key, workitem, data, ctx, scope)
    matched = _compare(observed, operator, expected)
    return ConditionMatch(
        matched=matched,
        reason=f"{field_key} {operator} {expected} (observed {observed})",
        evidence={field_key: _json_value(observed)},
    )


def _field_value(
    field_key: str,
    workitem: WorkItem,
    data: SignalData,
    ctx: EvaluationContext,
    scope: ScopeDescriptor,
) -> object:
    if field_key == "status":
        return workitem.status
    if field_key == "status_category":
        return workitem.status_category.value
    if field_key == "labels":
        return workitem.labels
    if field_key == "issue_type":
        return workitem.type.value
    if field_key == "assignee":
        return str(workitem.assignee_id) if workitem.assignee_id is not None else None
    if field_key == "created_at":
        return workitem.created_at
    if field_key == "updated_at":
        return workitem.updated_at
    if field_key == "resolved_at":
        return workitem.resolved_at
    if field_key == "age_since_created":
        return _age_days(ctx.now, workitem.created_at)
    if field_key == "age_since_updated":
        return _age_days(ctx.now, workitem.updated_at)
    if field_key == "age_in_current_status":
        return _age_days(ctx.now, _current_status_started_at(workitem, data.transitions))
    if field_key == "sprint_day":
        sprint = _current_sprint(workitem, data)
        if sprint is None or sprint.start_date is None:
            return None
        return max((ctx.now.date() - sprint.start_date.date()).days + 1, 1)
    if field_key == "sprint_phase":
        return _sprint_phase(workitem, data, ctx)
    if field_key == "priority":
        return None
    raise ExpressionValidationError(f"unsupported field: {field_key}")


def _compare(observed: object, operator: str, expected: object) -> bool:
    if operator == "is":
        return observed == expected
    if operator == "is_not":
        return observed != expected
    if operator == "is_any_of":
        return observed in _list(expected)
    if operator == "is_none_of":
        return observed not in _list(expected)
    if operator == "contains":
        return expected in _list(observed)
    if operator == "does_not_contain":
        return expected not in _list(observed)
    if operator == "contains_any":
        return bool(set(_list(observed)).intersection(_list(expected)))
    if operator == "does_not_contain_any":
        return not set(_list(observed)).intersection(_list(expected))
    if operator == "is_empty":
        return observed is None or observed == "" or observed == []
    if operator == "is_not_empty":
        return not _compare(observed, "is_empty", expected)
    if operator in {"greater_than", "less_than"}:
        left = _numeric(observed)
        right = _duration_days(expected)
        return left > right if operator == "greater_than" else left < right
    if operator == "between":
        left = _numeric(observed)
        low, high = _range(expected)
        return low <= left <= high
    if operator == "before":
        return isinstance(observed, datetime) and observed < _date_value(expected)
    if operator == "after":
        return isinstance(observed, datetime) and observed > _date_value(expected)
    if operator == "is_before":
        return _numeric(observed) < _numeric(expected)
    if operator == "is_after":
        return _numeric(observed) > _numeric(expected)
    return False


def _field_schema(schema: SignalCapabilitySchema, field_key: str) -> SignalField:
    for field_schema in schema.fields:
        if field_schema.key == field_key:
            return field_schema
    raise ExpressionValidationError(f"unknown field: {field_key}")


def _workitems_for_scope(data: SignalData, scope: ScopeDescriptor) -> list[WorkItem]:
    if scope.scope_type == "project":
        external_key = scope.external_ref.get("key")
        external_id = scope.external_ref.get("id")
        project_ids = {
            project.id
            for project in data.projects
            if project.key == external_key or project.external_id == external_id
        }
        return [item for item in data.workitems if item.project_id in project_ids]
    if scope.scope_type == "board":
        external_id = scope.external_ref.get("id")
        boards = [board for board in data.boards if board.external_id == external_id]
        board_ids = {board.id for board in boards}
        sprint_ids = {sprint.id for sprint in data.sprints if sprint.board_id in board_ids}
        if not sprint_ids:
            project_ids = {board.project_id for board in boards}
            return [item for item in data.workitems if item.project_id in project_ids]
        return [item for item in data.workitems if item.current_sprint_id in sprint_ids]
    return list(data.workitems)


def _scope_key(target: SignalTargetScope) -> str:
    return str(target.scope_id)


def _current_status_started_at(workitem: WorkItem, transitions: tuple[Transition, ...]) -> datetime:
    matching = [
        transition.occurred_at
        for transition in transitions
        if transition.entity_id == workitem.id
        and transition.to_status == workitem.status
        and transition.to_status_category is workitem.status_category
    ]
    return max(matching) if matching else workitem.updated_at


def _current_sprint(workitem: WorkItem, data: SignalData) -> Sprint | None:
    if workitem.current_sprint_id is None:
        return None
    return next(
        (sprint for sprint in data.sprints if sprint.id == workitem.current_sprint_id), None
    )


def _sprint_phase(workitem: WorkItem, data: SignalData, ctx: EvaluationContext) -> str | None:
    sprint = _current_sprint(workitem, data)
    if sprint is None or sprint.start_date is None or sprint.end_date is None:
        return None
    if ctx.now.date() <= sprint.start_date.date():
        return "first_day"
    if ctx.now.date() >= sprint.end_date.date():
        return "last_day"
    return "middle"


def _age_days(now: datetime, then: datetime | None) -> int | None:
    if then is None:
        return None
    return max((now - then).days, 0)


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else [value]


def _numeric(value: object) -> float:
    if value is None:
        return -1.0
    if isinstance(value, (int, float)):
        return float(value)
    raise ExpressionValidationError(f"{value!r} is not numeric")


def _duration_days(value: object) -> float:
    if isinstance(value, dict):
        amount = _numeric(value.get("amount"))
        unit = value.get("unit", "days")
        return amount / 24 if unit == "hours" else amount
    return _numeric(value)


def _range(value: object) -> tuple[float, float]:
    if isinstance(value, dict):
        return _duration_days(value.get("min")), _duration_days(value.get("max"))
    if isinstance(value, list) and len(value) == 2:
        return _duration_days(value[0]), _duration_days(value[1])
    raise ExpressionValidationError("between expects min/max or two values")


def _date_value(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ExpressionValidationError("date comparison expects an ISO datetime")


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
