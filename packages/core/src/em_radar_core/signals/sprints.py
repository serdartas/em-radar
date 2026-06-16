from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import Field, model_validator

from em_radar_core.models import (
    Confidence,
    EntityType,
    EvaluationContext,
    Severity,
    SignalFinding,
    Sprint,
    Transition,
    WorkItem,
)
from em_radar_core.signals.base import Signal, SignalData, SignalParams


class SprintScopeChurnParams(SignalParams):
    warning_pct: float = Field(default=20.0, ge=0.0)
    critical_pct: float = Field(default=35.0, ge=0.0)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "SprintScopeChurnParams":
        if self.critical_pct < self.warning_pct:
            raise ValueError("critical_pct must be greater than or equal to warning_pct")
        return self


class SprintScopeChurnSignal(Signal):
    id: ClassVar[str] = "sprint-scope-churn"
    name: ClassVar[str] = "Sprint scope churn"
    default_severity: ClassVar[Severity] = Severity.WARNING
    params_schema: ClassVar[type[SignalParams]] = SprintScopeChurnParams
    sprint_only: ClassVar[bool] = True

    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        params = SprintScopeChurnParams.model_validate(self.params)
        target_sprints = _target_sprints(data, ctx)
        transitions_by_item = _transitions_by_item(data.transitions)
        findings: list[SignalFinding] = []

        for sprint in target_sprints:
            if sprint.start_date is None:
                continue
            original_count, added_count = _scope_counts(
                sprint=sprint,
                workitems=data.workitems,
                transitions_by_item=transitions_by_item,
                now=ctx.now,
            )
            if original_count == 0:
                continue
            churn_pct = round((added_count / original_count) * 100, 2)
            if churn_pct < params.warning_pct:
                continue
            severity = (
                Severity.CRITICAL if churn_pct >= params.critical_pct else self.default_severity
            )
            findings.append(
                SignalFinding(
                    report_id=data.report_id,
                    signal_id=self.id,
                    signal_name=self.name,
                    severity=severity,
                    confidence=Confidence.HIGH,
                    entity_type=EntityType.SPRINT,
                    entity_id=sprint.id,
                    title=f"{sprint.name} scope churn is {churn_pct:g}%",
                    reason=f"{sprint.name} had items added after the sprint started.",
                    recommendation="Review sprint commitment changes with the team.",
                    evidence={
                        "original_count": original_count,
                        "added_count": added_count,
                        "churn_pct": churn_pct,
                    },
                    source_link=sprint.source_url,
                    created_at=ctx.now,
                )
            )

        return findings


def _target_sprints(data: SignalData, ctx: EvaluationContext) -> tuple[Sprint, ...]:
    if ctx.window.sprint_id is None:
        return data.sprints
    return tuple(sprint for sprint in data.sprints if sprint.id == ctx.window.sprint_id)


def _scope_counts(
    sprint: Sprint,
    workitems: tuple[WorkItem, ...],
    transitions_by_item: dict[UUID, tuple[Transition, ...]],
    now: datetime,
) -> tuple[int, int]:
    original_count = 0
    added_count = 0

    for item in workitems:
        if sprint.id not in item.sprint_ids:
            continue
        first_seen_at = _first_seen_at(item, transitions_by_item.get(item.id, ()))
        if first_seen_at is None or first_seen_at > now:
            continue
        if first_seen_at <= sprint.start_date:
            original_count += 1
        else:
            added_count += 1

    return original_count, added_count


def _first_seen_at(item: WorkItem, transitions: tuple[Transition, ...]) -> datetime | None:
    candidates = [transition.occurred_at for transition in transitions]
    if item.created_at is not None:
        candidates.append(item.created_at)
    if item.updated_at is not None:
        candidates.append(item.updated_at)
    return min(candidates) if candidates else None


def _transitions_by_item(
    transitions: tuple[Transition, ...],
) -> dict[UUID, tuple[Transition, ...]]:
    by_item: dict[UUID, list[Transition]] = {}
    for transition in transitions:
        if transition.entity_type is EntityType.WORKITEM:
            by_item.setdefault(transition.entity_id, []).append(transition)
    return {
        entity_id: tuple(sorted(entity_transitions, key=lambda transition: transition.occurred_at))
        for entity_id, entity_transitions in by_item.items()
    }
