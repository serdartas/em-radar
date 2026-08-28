# SPDX-License-Identifier: Apache-2.0

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import NamedTuple, TypeAlias

from em_radar_core.connectors import Capabilities, SignalCapabilitySchema, SignalField
from em_radar_core.models import (
    Confidence,
    EntityType,
    EvaluationContext,
    MergeRequest,
    MergeRequestSignalScope,
    Severity,
    SignalDefinition,
    SignalFinding,
    Sprint,
    Transition,
    WindowType,
    WorkItem,
    WorkItemType,
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
    connector_capabilities: Capabilities | None = None


@dataclass(frozen=True)
class ConditionMatch:
    matched: bool
    reason: str
    evidence: JsonObject


@dataclass(frozen=True)
class SignalSkipNote:
    signal_id: str
    reason: str


_SPRINT_FIELDS: frozenset[str] = frozenset(
    {"sprint_count", "sprint_day", "sprint_phase", "sprint_scope_added_pct"}
)

# Maps expression field keys to (Capabilities attribute, human-readable reason).
# When a signal's expression uses a field in this map and the connector reports the
# corresponding capability as False, the signal is skipped with the given reason.
_FIELD_CONNECTOR_CAPABILITY_MAP: dict[str, tuple[str, str]] = {
    "age_in_current_status": (
        "provides_transitions",
        "requires status-transition history from the connector",
    ),
    "sprint_scope_added_pct": (
        "provides_transitions",
        "requires status-transition history from the connector",
    ),
}

CUSTOM_FIELD_OPERATORS: frozenset[str] = frozenset(
    {
        "is",
        "is_not",
        "greater_than",
        "less_than",
        "is_empty",
        "is_not_empty",
        "contains",
        "does_not_contain",
    }
)

# Custom field ids follow Jira's ``customfield_<n>`` shape; gating the custom-field fallback
# on this pattern keeps misspelled built-in field names from being silently accepted.
_CUSTOM_FIELD_KEY_PATTERN = re.compile(r"customfield_\d+")


def is_custom_field_key(field_key: str) -> bool:
    """Return True when a key matches Jira's ``customfield_<n>`` custom-field id shape."""
    return _CUSTOM_FIELD_KEY_PATTERN.fullmatch(field_key) is not None


class ExpressionValidationError(ValueError):
    pass


def check_capability_gate(
    definition: SignalDefinition,
    capabilities: Capabilities,
) -> SignalSkipNote | None:
    """Return a skip note when the definition requires connector capabilities that are absent."""
    for leaf in leaf_conditions(definition.expression):
        field_key = leaf.get("field")
        if not isinstance(field_key, str):
            continue
        cap_entry = _FIELD_CONNECTOR_CAPABILITY_MAP.get(field_key)
        if cap_entry is not None:
            cap_attr, reason = cap_entry
            if not getattr(capabilities, cap_attr):
                return SignalSkipNote(signal_id=str(definition.id), reason=reason)
    return None


def _uses_sprint_fields(expression: JsonObject) -> bool:
    """Return True when any leaf condition in the expression references a sprint-specific field."""
    for leaf in leaf_conditions(expression):
        if leaf.get("field") in _SPRINT_FIELDS:
            return True
    return False


def check_window_gate(
    definition: SignalDefinition,
    ctx: EvaluationContext,
) -> SignalSkipNote | None:
    """Return a skip note when a sprint-field signal runs outside a sprint window, else None."""
    if definition.expression is None or not _uses_sprint_fields(definition.expression):
        return None
    if ctx.window.window_type is WindowType.SPRINT:
        return None
    return SignalSkipNote(
        signal_id=str(definition.id),
        reason="requires a sprint window",
    )


def _guarantees_link_emptiness(expression: object) -> bool:
    """Return True when every match of the expression has an empty ``linked_workitem_keys``.

    Section metadata is signal-wide, so link-emptiness must be guaranteed for all matches:
    a mandatory ``all`` conjunct suffices, but every branch of an ``any`` must guarantee it.
    """
    if not isinstance(expression, dict):
        return False
    if expression.get("type") != "group":
        return (
            expression.get("field") == "linked_workitem_keys"
            and expression.get("operator") == "is_empty"
        )
    conditions = expression.get("conditions")
    if not isinstance(conditions, list):
        return False
    checks = [_guarantees_link_emptiness(c) for c in conditions if isinstance(c, dict)]
    if not checks:
        return False
    operator = expression.get("operator")
    if operator == "all":
        return any(checks)
    if operator == "any":
        return all(checks)
    return False


def is_source_linking_signal(definition: SignalDefinition) -> bool:
    """Return True when the definition flags entities missing a linked work item.

    A source-linking signal's expression guarantees an empty ``linked_workitem_keys``
    for every match (see ``_guarantees_link_emptiness``). Detecting it here lets
    user-created signals (no template key) route their findings to the Source Linking
    report section.
    """
    return _guarantees_link_emptiness(definition.expression)


def resolve_severity(
    per_signal: str | None,
    pack_override: str | None = None,
    template_default: str | None = None,
) -> Severity:
    """Return effective severity following spec §8: per-signal → pack override → template default.

    No tier escalates based on observed data — severity is a fixed property of the signal
    configuration, not a dynamic outcome of evaluation.
    """
    for candidate in (per_signal, pack_override, template_default):
        if candidate is not None:
            return Severity(candidate)
    return Severity.WARNING


def evaluate_signal_definition(
    definition: SignalDefinition,
    data: SignalData,
    ctx: EvaluationContext,
    schema: SignalCapabilitySchema,
    scopes: list[ScopeDescriptor],
) -> list[SignalFinding]:
    if not scopes:
        return []

    if check_window_gate(definition, ctx) is not None:
        return []

    for scope in scopes:
        if scope.connector_capabilities is not None:
            if check_capability_gate(definition, scope.connector_capabilities) is not None:
                return []
            break

    validate_expression(definition.expression, schema, scopes)

    # Pack and template severity tiers are resolved at seed/import time (via apply_pack_defaults
    # and the signal catalog). By the time a SignalDefinition reaches the evaluator its
    # report_settings.severity already holds the fully resolved value; the evaluator always
    # reads from that single canonical field via resolve_severity.
    severity = resolve_severity(definition.report_settings.severity)

    if definition.entity_type == "merge_request":
        return _evaluate_mr_signal(definition, data, ctx, severity, scopes)

    if definition.entity_type == "sprint":
        return _evaluate_sprint_signal(definition, data, ctx, severity, scopes)

    findings: list[SignalFinding] = []
    for scope in scopes:
        for workitem in _workitems_for_scope(data, scope, ctx):
            result = _evaluate_group(definition.expression, workitem, data, ctx, scope)
            if not result.matched:
                continue
            findings.append(
                SignalFinding(
                    report_id=data.report_id,
                    signal_id=str(definition.id),
                    signal_name=definition.name,
                    severity=severity,
                    confidence=Confidence.HIGH,
                    entity_type=EntityType.WORKITEM,
                    entity_id=workitem.id,
                    title=f"{workitem.key} - {workitem.title}",
                    reason=result.reason,
                    scope_name=scope.name,
                    evidence={"scope_id": scope.scope_id, **result.evidence},
                    source_link=workitem.source_url,
                    created_at=ctx.now,
                )
            )
    return findings


def _evaluate_mr_signal(
    definition: SignalDefinition,
    data: SignalData,
    ctx: EvaluationContext,
    severity: Severity,
    _scopes: list[ScopeDescriptor],
) -> list[SignalFinding]:
    """Evaluate a merge_request entity signal over MergeRequest entities filtered by scope.

    The signal's ``report_settings.mr_scope`` determines which MRs are evaluated:
    - ``TEAM_REPOSITORIES`` (default): all MRs in ``data.mergerequests`` (already repo-scoped
      by the runner from M9-06).
    - ``AUTHORED_BY_MEMBERS``: only MRs whose ``author_id`` is in
      ``data.team_member_author_ids``.
    The ``scope_name`` on each finding reflects the signal's own scope, not the connector
    scope descriptor, so reports display the actual scope used per signal (§19).
    """
    mr_scope = definition.report_settings.mr_scope or MergeRequestSignalScope.TEAM_REPOSITORIES
    if mr_scope is MergeRequestSignalScope.AUTHORED_BY_MEMBERS:
        scope_name = "MRs authored by team members"
        mrs: list[MergeRequest] = [
            mr for mr in data.mergerequests if mr.author_id in data.team_member_author_ids
        ]
    else:
        scope_name = "MRs in team-owned repositories"
        mrs = list(data.mergerequests)
    findings: list[SignalFinding] = []
    for mr in mrs:
        result = _evaluate_mr_group(definition.expression, mr, data, ctx)
        if not result.matched:
            continue
        findings.append(
            SignalFinding(
                report_id=data.report_id,
                signal_id=str(definition.id),
                signal_name=definition.name,
                severity=severity,
                confidence=Confidence.HIGH,
                entity_type=EntityType.MERGEREQUEST,
                entity_id=mr.id,
                title=f"!{mr.iid} - {mr.title}",
                reason=result.reason,
                evidence=result.evidence,
                source_link=mr.source_url,
                scope_name=scope_name,
                created_at=ctx.now,
            )
        )
    return findings


def _evaluate_sprint_signal(
    definition: SignalDefinition,
    data: SignalData,
    ctx: EvaluationContext,
    severity: Severity,
    scopes: list[ScopeDescriptor],
) -> list[SignalFinding]:
    """Evaluate a sprint entity signal over board sprints in scope.

    When the evaluation window is a sprint window, only the target sprint is evaluated;
    otherwise all board sprints are evaluated.
    """
    target_sprint_id = ctx.window.sprint_id if ctx.window.window_type is WindowType.SPRINT else None
    findings: list[SignalFinding] = []
    for scope in scopes:
        if scope.scope_type != "board":
            continue
        external_id = scope.external_ref.get("id")
        board_ids = {board.id for board in data.boards if board.external_id == external_id}
        for sprint in data.sprints:
            if sprint.board_id not in board_ids:
                continue
            if target_sprint_id is not None and sprint.id != target_sprint_id:
                continue
            result = _evaluate_sprint_group(definition.expression, sprint, data, ctx)
            if not result.matched:
                continue
            findings.append(
                SignalFinding(
                    report_id=data.report_id,
                    signal_id=str(definition.id),
                    signal_name=definition.name,
                    severity=severity,
                    confidence=Confidence.HIGH,
                    entity_type=EntityType.SPRINT,
                    entity_id=sprint.id,
                    title=sprint.name,
                    reason=result.reason,
                    scope_name=scope.name,
                    evidence={"scope_id": scope.scope_id, **result.evidence},
                    source_link=sprint.source_url,
                    created_at=ctx.now,
                )
            )
    return findings


def _evaluate_sprint_group(
    expression: JsonObject,
    sprint: Sprint,
    data: SignalData,
    ctx: EvaluationContext,
) -> ConditionMatch:
    if expression.get("type") != "group":
        return _evaluate_sprint_condition(expression, sprint, data, ctx)
    conditions = [item for item in expression["conditions"] if isinstance(item, dict)]
    matches = [_evaluate_sprint_group(condition, sprint, data, ctx) for condition in conditions]
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


def _evaluate_sprint_condition(
    condition: JsonObject,
    sprint: Sprint,
    data: SignalData,
    ctx: EvaluationContext,
) -> ConditionMatch:
    field_key = str(condition["field"])
    operator = str(condition["operator"])
    expected = condition.get("value")
    evidence: JsonObject
    if field_key == "sprint_scope_added_pct":
        churn = _sprint_scope_churn(sprint, data, ctx)
        observed: object = churn.pct if churn is not None else None
        if churn is not None:
            evidence = {
                "original_count": churn.original_count,
                "added_count": churn.added_count,
                "churn_pct": _json_value(churn.pct),
            }
        else:
            evidence = {}
    else:
        raise ExpressionValidationError(f"unsupported sprint field: {field_key}")
    matched = _compare(observed, operator, expected)
    return ConditionMatch(
        matched=matched,
        reason=f"{field_key} {operator} {expected} (observed {observed})",
        evidence=evidence,
    )


class _ChurnResult(NamedTuple):
    pct: float
    original_count: int
    added_count: int


def _sprint_scope_churn(
    sprint: Sprint, data: SignalData, ctx: EvaluationContext
) -> _ChurnResult | None:
    """Compute sprint scope churn, returning pct and constituent counts or None.

    Returns None when sprint has no start_date or no items, so numeric operators
    correctly produce no match. Uses sprint_ids (not current_sprint_id) to match
    items that were part of the sprint even if later moved to another sprint.
    """
    if sprint.start_date is None:
        return None
    sprint_items = [wi for wi in data.workitems if sprint.id in wi.sprint_ids]
    if not sprint_items:
        return None
    now = _as_utc(ctx.now)
    start = _as_utc(sprint.start_date)
    original = 0
    valid_count = 0
    for wi in sprint_items:
        first_seen = _first_seen_at(wi, data)
        if first_seen is None or first_seen > now:
            continue  # unknown or future-dated — exclude from both numerator and denominator
        valid_count += 1
        if first_seen <= start:
            original += 1
    added = valid_count - original
    if original == 0:
        return None
    return _ChurnResult(
        pct=round(added / original * 100.0, 2), original_count=original, added_count=added
    )


def _first_seen_at(wi: WorkItem, data: SignalData) -> datetime | None:
    """Return the first-seen datetime: min(transition occurred_at, created_at). updated_at excluded."""
    candidates = [t.occurred_at for t in data.transitions if t.entity_id == wi.id]
    if wi.created_at is not None:
        candidates.append(wi.created_at)
    if not candidates:
        return None
    return min(_as_utc(candidate) for candidate in candidates)


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
        # Skip window-gating so sprint signals preview correctly with a date-range context.
        findings = _evaluate_without_window_gate(definition, data, ctx, schema, scopes)
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


def _evaluate_without_window_gate(
    definition: SignalDefinition,
    data: SignalData,
    ctx: EvaluationContext,
    schema: SignalCapabilitySchema,
    scopes: list[ScopeDescriptor],
) -> list[SignalFinding]:
    """Like evaluate_signal_definition but skips check_window_gate — used by preview."""
    if not scopes:
        return []

    for scope in scopes:
        if scope.connector_capabilities is not None:
            if check_capability_gate(definition, scope.connector_capabilities) is not None:
                return []
            break

    validate_expression(definition.expression, schema, scopes)

    severity = resolve_severity(definition.report_settings.severity)

    if definition.entity_type == "merge_request":
        return _evaluate_mr_signal(definition, data, ctx, severity, scopes)

    if definition.entity_type == "sprint":
        return _evaluate_sprint_signal(definition, data, ctx, severity, scopes)

    findings: list[SignalFinding] = []
    for scope in scopes:
        for workitem in _workitems_for_scope(data, scope, ctx):
            result = _evaluate_group(definition.expression, workitem, data, ctx, scope)
            if not result.matched:
                continue
            findings.append(
                SignalFinding(
                    report_id=data.report_id,
                    signal_id=str(definition.id),
                    signal_name=definition.name,
                    severity=severity,
                    confidence=Confidence.HIGH,
                    entity_type=EntityType.WORKITEM,
                    entity_id=workitem.id,
                    title=f"{workitem.key} - {workitem.title}",
                    reason=result.reason,
                    scope_name=scope.name,
                    evidence={"scope_id": scope.scope_id, **result.evidence},
                    source_link=workitem.source_url,
                    created_at=ctx.now,
                )
            )
    return findings


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
    # Check built-in fields first (collision guard).
    field_schema = _field_schema_or_none(schema, field_key)
    if field_schema is not None:
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
    else:
        # Unknown field: treat as a custom field only when the key has the customfield_<n>
        # shape; a misspelled built-in name (e.g. "statuss") must still raise.
        if not is_custom_field_key(field_key):
            raise ExpressionValidationError(f"unknown field: {field_key}")
        if operator not in CUSTOM_FIELD_OPERATORS:
            raise ExpressionValidationError(f"{operator} is not valid for custom field {field_key}")


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
    if field_key == "components":
        return workitem.components
    if field_key == "story_points":
        return workitem.story_points
    if field_key == "workitem_types":
        return workitem.type.value
    if field_key == "issue_type":
        return workitem.type.value
    if field_key == "branches":
        return None
    if field_key == "assignee":
        return str(workitem.assignee_id) if workitem.assignee_id is not None else None
    if field_key == "acceptance_criteria":
        return workitem.acceptance_criteria
    if field_key == "parent_id":
        return str(workitem.parent_id) if workitem.parent_id is not None else None
    if field_key == "has_epic_parent":
        if workitem.parent_id is None:
            return False
        parent = next((item for item in data.workitems if item.id == workitem.parent_id), None)
        if parent is None:
            # Parent is outside the fetched scope (e.g. cross-project epic).
            # Return None to indicate unknown rather than incorrectly signalling False.
            return None
        return parent.type is WorkItemType.EPIC
    if field_key == "description_length":
        return len(workitem.description or "")
    if field_key == "child_count":
        return sum(1 for item in data.workitems if item.parent_id == workitem.id)
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
    if field_key == "sprint_count":
        return len(tuple(dict.fromkeys(workitem.sprint_ids)))
    return workitem.custom_fields.get(field_key)


def _evaluate_mr_group(
    expression: JsonObject,
    mr: MergeRequest,
    data: SignalData,
    ctx: EvaluationContext,
) -> ConditionMatch:
    if expression.get("type") != "group":
        return _evaluate_mr_condition(expression, mr, data, ctx)
    conditions = [item for item in expression["conditions"] if isinstance(item, dict)]
    matches = [_evaluate_mr_group(condition, mr, data, ctx) for condition in conditions]
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


def _evaluate_mr_condition(
    condition: JsonObject,
    mr: MergeRequest,
    data: SignalData,
    ctx: EvaluationContext,
) -> ConditionMatch:
    field_key = str(condition["field"])
    operator = str(condition["operator"])
    expected = condition.get("value")
    observed = _mr_field_value(field_key, mr, data, ctx)
    matched = _compare(observed, operator, expected)
    return ConditionMatch(
        matched=matched,
        reason=f"{field_key} {operator} {expected} (observed {observed})",
        evidence={field_key: _json_value(observed)},
    )


def _mr_field_value(
    field_key: str,
    mr: MergeRequest,
    data: SignalData,
    ctx: EvaluationContext,
) -> object:
    if field_key == "state":
        return mr.state.value
    if field_key == "is_draft":
        return mr.is_draft
    if field_key == "title":
        return mr.title
    if field_key == "source_branch":
        return mr.source_branch
    if field_key == "target_branch":
        return mr.target_branch
    if field_key == "changed_files_count":
        return mr.changed_files_count
    if field_key == "total_changes":
        if mr.additions is None and mr.deletions is None:
            return None
        return (mr.additions or 0) + (mr.deletions or 0)
    if field_key == "pipeline_status":
        return mr.pipeline_status.value if mr.pipeline_status is not None else "none"
    if field_key == "age_since_pipeline_update":
        return _age_days(ctx.now, mr.pipeline_updated_at)
    if field_key == "approval_count":
        return mr.approval_count
    if field_key == "linked_workitem_keys":
        return mr.linked_workitem_keys
    if field_key == "created_at":
        return mr.created_at
    if field_key == "updated_at":
        return mr.updated_at
    if field_key == "merged_at":
        return mr.merged_at
    if field_key == "closed_at":
        return mr.closed_at
    if field_key == "age_since_created":
        return _age_days(ctx.now, mr.created_at)
    if field_key == "age_since_updated":
        return _age_days(ctx.now, mr.updated_at)
    if field_key == "age_since_last_review_activity":
        submitted = [
            r.submitted_at
            for r in data.reviews
            if r.mergerequest_id == mr.id and r.submitted_at is not None
        ]
        return _age_days(ctx.now, max(submitted) if submitted else mr.created_at)
    raise ExpressionValidationError(f"unsupported MR field: {field_key}")


def _compare(observed: object, operator: str, expected: object) -> bool:
    if operator == "is":
        return observed is not None and observed == expected
    if operator == "is_not":
        return observed is not None and observed != expected
    if operator == "is_any_of":
        return observed in _list(expected)
    if operator == "is_none_of":
        return observed not in _list(expected)
    if operator == "contains":
        if isinstance(observed, str) and isinstance(expected, str):
            return expected in observed
        return expected in _list(observed)
    if operator == "does_not_contain":
        if isinstance(observed, str) and isinstance(expected, str):
            return expected not in observed
        return expected not in _list(observed)
    if operator == "contains_any":
        return bool(set(_list(observed)).intersection(_list(expected)))
    if operator == "does_not_contain_any":
        return not set(_list(observed)).intersection(_list(expected))
    if operator == "is_empty":
        return observed is None or observed == "" or observed == []
    if operator == "is_not_empty":
        return not _compare(observed, "is_empty", expected)
    if (
        operator
        in {
            "greater_than",
            "less_than",
            "between",
            "before",
            "after",
            "is_before",
            "is_after",
            "gt",
            "lt",
            "gte",
            "lte",
            "eq",
            "neq",
        }
        and observed is None
    ):
        return False
    if operator in {"gt", "lt", "gte", "lte", "eq", "neq"}:
        left = _numeric_or_none(observed)
        if left is None:
            return False
        right = _numeric(expected)
        if operator == "gt":
            return left > right
        if operator == "lt":
            return left < right
        if operator == "gte":
            return left >= right
        if operator == "lte":
            return left <= right
        if operator == "eq":
            return left == right
        return left != right
    if operator in {"greater_than", "less_than"}:
        left = _numeric_or_none(observed)
        if left is None:
            return False
        right = _duration_days(expected)
        return left > right if operator == "greater_than" else left < right
    if operator == "between":
        if isinstance(observed, datetime) or _is_date_range(expected):
            if not isinstance(observed, datetime):
                return False
            start, end = _date_range(value=expected)
            obs = _coerce_tz(observed, start)
            return start <= obs <= end
        left = _numeric(observed)
        low, high = _range(expected)
        return low <= left <= high
    if operator == "before":
        if not isinstance(observed, datetime):
            return False
        ref = _date_value(expected)
        return _coerce_tz(observed, ref) < ref
    if operator == "after":
        if not isinstance(observed, datetime):
            return False
        ref = _date_value(expected)
        return _coerce_tz(observed, ref) > ref
    if operator == "is_before":
        return _numeric(observed) < _numeric(expected)
    if operator == "is_after":
        return _numeric(observed) > _numeric(expected)
    if operator == "matches_glob":
        if observed is None or not isinstance(expected, str):
            return False
        return fnmatch.fnmatchcase(str(observed), expected)
    return False


def _field_schema_or_none(schema: SignalCapabilitySchema, field_key: str) -> SignalField | None:
    for field_schema in schema.fields:
        if field_schema.key == field_key:
            return field_schema
    return None


def _field_schema(schema: SignalCapabilitySchema, field_key: str) -> SignalField:
    result = _field_schema_or_none(schema, field_key)
    if result is None:
        raise ExpressionValidationError(f"unknown field: {field_key}")
    return result


def _workitems_for_scope(
    data: SignalData, scope: ScopeDescriptor, ctx: EvaluationContext
) -> list[WorkItem]:
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
        # For non-zero DATE_RANGE windows, use the board's project scope so historical
        # items in the range are evaluated — not just items currently assigned to a sprint.
        # Zero-length windows (start == end) are preview placeholders and must retain
        # sprint/board scoping to avoid misleading match counts in the preview route.
        w = ctx.window
        if (
            w.window_type is WindowType.DATE_RANGE
            and w.start is not None
            and w.end is not None
            and w.start < w.end
        ):
            project_ids = {board.project_id for board in boards}
            return [item for item in data.workitems if item.project_id in project_ids]
        sprint_ids = {sprint.id for sprint in data.sprints if sprint.board_id in board_ids}
        if not sprint_ids:
            project_ids = {board.project_id for board in boards}
            return [item for item in data.workitems if item.project_id in project_ids]
        return [item for item in data.workitems if item.current_sprint_id in sprint_ids]
    return list(data.workitems)


def _current_status_started_at(
    workitem: WorkItem, transitions: tuple[Transition, ...]
) -> datetime | None:
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


def _age_days(now: datetime, then: datetime | None) -> float | None:
    if then is None:
        return None
    if now.tzinfo is not None and then.tzinfo is None:
        then = then.replace(tzinfo=now.tzinfo)
    elif now.tzinfo is None and then.tzinfo is not None:
        now = now.replace(tzinfo=then.tzinfo)
    return max((now - then).total_seconds() / 86400.0, 0.0)


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else [value]


def _numeric(value: object) -> float:
    if value is None:
        raise ExpressionValidationError("cannot compare: field value is null")
    if isinstance(value, bool):
        raise ExpressionValidationError(f"{value!r} is not numeric")
    if isinstance(value, (int, float)):
        return float(value)
    raise ExpressionValidationError(f"{value!r} is not numeric")


def _numeric_or_none(value: object) -> float | None:
    """Coerce an observed field value to float, or None when it is null/bool/non-numeric.

    Used for observed operands so a numeric operator on a non-numeric custom-field value
    produces a no-match instead of aborting the whole report.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


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
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    raise ExpressionValidationError("date comparison expects an ISO datetime")


def _date_range(value: object) -> tuple[datetime, datetime]:
    if isinstance(value, dict):
        start = value.get("start") or value.get("min")
        end = value.get("end") or value.get("max")
        return _date_value(start), _date_value(end)
    if isinstance(value, list) and len(value) == 2:
        return _date_value(value[0]), _date_value(value[1])
    raise ExpressionValidationError("date between expects start/end or two ISO datetimes")


def _coerce_tz(observed: datetime, reference: datetime) -> datetime:
    """Return observed as UTC-aware when naive, enabling comparison with a tz-aware reference."""
    if observed.tzinfo is None and reference.tzinfo is not None:
        return observed.replace(tzinfo=timezone.utc)
    return observed


def _as_utc(value: datetime) -> datetime:
    """Return value as UTC-aware, assuming UTC when naive, so comparisons never mix tz-awareness."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _is_date_like(value: object) -> bool:
    if isinstance(value, datetime):
        return True
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
            return True
        except ValueError:
            return False
    return False


def _is_date_range(value: object) -> bool:
    """Return True when value describes a date range rather than a numeric range."""
    if isinstance(value, list) and len(value) == 2:
        return _is_date_like(value[0]) or _is_date_like(value[1])
    if isinstance(value, dict):
        candidate = value.get("start") or value.get("end") or value.get("min") or value.get("max")
        return _is_date_like(candidate)
    return False


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def leaf_conditions(expression: JsonObject) -> list[JsonObject]:
    if expression.get("type") != "group":
        return [expression]
    conditions = expression.get("conditions")
    if not isinstance(conditions, list):
        return []
    return [
        leaf
        for condition in conditions
        if isinstance(condition, dict)
        for leaf in leaf_conditions(condition)
    ]
