from collections import Counter
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from em_radar_core.models import (
    Confidence,
    EntityType,
    EvaluationContext,
    Severity,
    SignalFinding,
    Sprint,
    StatusCategory,
    Transition,
    WorkItem,
    WorkItemType,
)
from em_radar_core.signals.base import Signal, SignalData, SignalParams


class BlockedWithoutUpdateParams(SignalParams):
    days_threshold: int = Field(default=3, ge=0)


class StoryWithoutAcceptanceCriteriaParams(SignalParams):
    pass


class StoryWithoutParentEpicParams(SignalParams):
    pass


class EpicTooBroadParams(SignalParams):
    max_children: int = Field(default=15, ge=0)


class EpicWithoutMeasurableDescriptionParams(SignalParams):
    min_description_length: int = Field(default=100, ge=0)


class RepeatedCarryOverParams(SignalParams):
    min_sprint_count: int = Field(default=2, ge=1)


class BlockedWithoutUpdateSignal(Signal):
    id: ClassVar[str] = "blocked-without-update"
    name: ClassVar[str] = "Blocked without update"
    default_severity: ClassVar[Severity] = Severity.CRITICAL
    params_schema: ClassVar[type[SignalParams]] = BlockedWithoutUpdateParams

    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        params = BlockedWithoutUpdateParams.model_validate(self.params)
        transitions_by_item = _workitem_transitions_by_entity(data.transitions)
        findings: list[SignalFinding] = []

        for item in data.workitems:
            transitions = transitions_by_item.get(item.id, ())
            if not _is_blocked(item, transitions):
                continue
            last_updated_at = _last_updated_at(item, transitions)
            if last_updated_at is None:
                continue
            days_blocked_idle = (ctx.now - last_updated_at).days
            if days_blocked_idle < params.days_threshold:
                continue
            findings.append(
                _workitem_finding(
                    data=data,
                    ctx=ctx,
                    signal=self,
                    item=item,
                    title=f"{item.key} blocked for {days_blocked_idle} idle days",
                    reason=f"{item.key} is blocked and has not been updated recently.",
                    recommendation="Review the blocker and record the next action.",
                    evidence={
                        "days_blocked_idle": days_blocked_idle,
                        "last_updated_at": last_updated_at.isoformat(),
                        "threshold": params.days_threshold,
                    },
                )
            )

        return findings


class StoryWithoutAcceptanceCriteriaSignal(Signal):
    id: ClassVar[str] = "story-without-acceptance-criteria"
    name: ClassVar[str] = "Story without acceptance criteria"
    default_severity: ClassVar[Severity] = Severity.WARNING
    params_schema: ClassVar[type[SignalParams]] = StoryWithoutAcceptanceCriteriaParams

    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        findings: list[SignalFinding] = []

        for item in data.workitems:
            if item.type is not WorkItemType.STORY or _has_text(item.acceptance_criteria):
                continue
            findings.append(
                _workitem_finding(
                    data=data,
                    ctx=ctx,
                    signal=self,
                    item=item,
                    title=f"{item.key} has no acceptance criteria",
                    reason=f"{item.key} is a story without acceptance criteria.",
                    recommendation="Add clear acceptance criteria before delivery starts.",
                    evidence={
                        "workitem_type": item.type.value,
                        "has_description": _has_text(item.description),
                    },
                )
            )

        return findings


class StoryWithoutParentEpicSignal(Signal):
    id: ClassVar[str] = "story-without-parent-epic"
    name: ClassVar[str] = "Story without parent epic"
    default_severity: ClassVar[Severity] = Severity.INFO
    params_schema: ClassVar[type[SignalParams]] = StoryWithoutParentEpicParams

    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        findings: list[SignalFinding] = []

        for item in data.workitems:
            if item.type is not WorkItemType.STORY or item.parent_id is not None:
                continue
            findings.append(
                _workitem_finding(
                    data=data,
                    ctx=ctx,
                    signal=self,
                    item=item,
                    title=f"{item.key} has no parent epic",
                    reason=f"{item.key} is a story without a parent epic link.",
                    recommendation="Link the story to the relevant epic.",
                    evidence={"workitem_type": item.type.value},
                )
            )

        return findings


class EpicTooBroadSignal(Signal):
    id: ClassVar[str] = "epic-too-broad"
    name: ClassVar[str] = "Epic too broad"
    default_severity: ClassVar[Severity] = Severity.WARNING
    params_schema: ClassVar[type[SignalParams]] = EpicTooBroadParams

    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        params = EpicTooBroadParams.model_validate(self.params)
        child_counts = Counter(item.parent_id for item in data.workitems if item.parent_id)
        findings: list[SignalFinding] = []

        for item in data.workitems:
            if item.type is not WorkItemType.EPIC:
                continue
            child_count = child_counts[item.id]
            if child_count <= params.max_children:
                continue
            findings.append(
                _workitem_finding(
                    data=data,
                    ctx=ctx,
                    signal=self,
                    item=item,
                    title=f"{item.key} has {child_count} child items",
                    reason=f"{item.key} has more child items than the configured threshold.",
                    recommendation="Split or clarify the epic scope.",
                    evidence={"child_count": child_count, "threshold": params.max_children},
                )
            )

        return findings


class EpicWithoutMeasurableDescriptionSignal(Signal):
    id: ClassVar[str] = "epic-without-measurable-description"
    name: ClassVar[str] = "Epic without measurable description"
    default_severity: ClassVar[Severity] = Severity.INFO
    params_schema: ClassVar[type[SignalParams]] = EpicWithoutMeasurableDescriptionParams

    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        params = EpicWithoutMeasurableDescriptionParams.model_validate(self.params)
        findings: list[SignalFinding] = []

        for item in data.workitems:
            if item.type is not WorkItemType.EPIC:
                continue
            description_length = len(item.description or "")
            if description_length >= params.min_description_length:
                continue
            findings.append(
                _workitem_finding(
                    data=data,
                    ctx=ctx,
                    signal=self,
                    item=item,
                    title=f"{item.key} has a short epic description",
                    reason=f"{item.key} does not have enough description detail.",
                    recommendation="Describe the measurable outcome and boundary of the epic.",
                    evidence={
                        "description_length": description_length,
                        "threshold": params.min_description_length,
                    },
                )
            )

        return findings


class RepeatedCarryOverSignal(Signal):
    id: ClassVar[str] = "repeated-carry-over"
    name: ClassVar[str] = "Repeated carry-over"
    default_severity: ClassVar[Severity] = Severity.WARNING
    params_schema: ClassVar[type[SignalParams]] = RepeatedCarryOverParams
    sprint_only: ClassVar[bool] = True

    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        params = RepeatedCarryOverParams.model_validate(self.params)
        sprint_names = {sprint.id: sprint.name for sprint in data.sprints}
        findings: list[SignalFinding] = []

        for item in data.workitems:
            if item.status_category is StatusCategory.DONE:
                continue
            sprint_ids = tuple(dict.fromkeys(item.sprint_ids))
            if len(sprint_ids) < params.min_sprint_count:
                continue
            names = [
                sprint_names[sprint_id] for sprint_id in sprint_ids if sprint_id in sprint_names
            ]
            findings.append(
                _workitem_finding(
                    data=data,
                    ctx=ctx,
                    signal=self,
                    item=item,
                    title=f"{item.key} carried over across {len(sprint_ids)} sprints",
                    reason=f"{item.key} has appeared in multiple sprints without completing.",
                    recommendation="Review scope, blockers, or split the work item.",
                    evidence={"sprint_count": len(sprint_ids), "sprint_names": names},
                )
            )

        return findings


def _workitem_finding(
    data: SignalData,
    ctx: EvaluationContext,
    signal: Signal,
    item: WorkItem,
    title: str,
    reason: str,
    recommendation: str,
    evidence: dict[str, object],
) -> SignalFinding:
    return SignalFinding(
        report_id=data.report_id,
        signal_id=signal.id,
        signal_name=signal.name,
        severity=signal.default_severity,
        confidence=Confidence.HIGH,
        entity_type=EntityType.WORKITEM,
        entity_id=item.id,
        title=title,
        reason=reason,
        recommendation=recommendation,
        evidence=evidence,
        source_link=item.source_url,
        created_at=ctx.now,
    )


def _workitem_transitions_by_entity(
    transitions: tuple[Transition, ...],
) -> dict[UUID, tuple[Transition, ...]]:
    by_entity: dict[UUID, list[Transition]] = {}
    for transition in transitions:
        if transition.entity_type is not EntityType.WORKITEM:
            continue
        by_entity.setdefault(transition.entity_id, []).append(transition)
    return {
        entity_id: tuple(sorted(entity_transitions, key=lambda transition: transition.occurred_at))
        for entity_id, entity_transitions in by_entity.items()
    }


def _is_blocked(item: WorkItem, transitions: tuple[Transition, ...]) -> bool:
    if item.is_blocked or item.status_category is StatusCategory.BLOCKED:
        return True
    if not transitions:
        return False
    return transitions[-1].to_status_category is StatusCategory.BLOCKED


def _last_updated_at(item: WorkItem, transitions: tuple[Transition, ...]) -> datetime | None:
    candidates = [transition.occurred_at for transition in transitions]
    if item.updated_at is not None:
        candidates.append(item.updated_at)
    return max(candidates) if candidates else None


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def sprint_by_id(sprints: tuple[Sprint, ...]) -> dict[UUID, Sprint]:
    return {sprint.id: sprint for sprint in sprints}
