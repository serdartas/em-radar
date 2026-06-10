from typing import ClassVar

from pydantic import Field

from em_radar_core.models import (
    Confidence,
    EntityType,
    EvaluationContext,
    Severity,
    SignalFinding,
    StatusCategory,
    WorkItem,
)
from em_radar_core.signals.base import Signal, SignalData, SignalParams


class StaleInProgressParams(SignalParams):
    days_threshold: int = Field(default=7, ge=0)
    exclude_labels: list[str] = Field(default_factory=list)


class StaleInProgressSignal(Signal):
    id: ClassVar[str] = "stale-in-progress-work-item"
    name: ClassVar[str] = "Stale in-progress work item"
    default_severity: ClassVar[Severity] = Severity.WARNING
    params_schema: ClassVar[type[SignalParams]] = StaleInProgressParams

    def evaluate(self, data: SignalData, ctx: EvaluationContext) -> list[SignalFinding]:
        params = StaleInProgressParams.model_validate(self.params)
        excluded_labels = set(params.exclude_labels)
        findings: list[SignalFinding] = []

        for item in data.workitems:
            if not self._is_candidate(item, excluded_labels):
                continue
            assert item.updated_at is not None
            days_idle = (ctx.now - item.updated_at).days
            if days_idle < params.days_threshold:
                continue
            findings.append(self._finding(data, ctx, item, days_idle, params.days_threshold))

        return findings

    @staticmethod
    def _is_candidate(item: WorkItem, excluded_labels: set[str]) -> bool:
        return (
            item.status_category is StatusCategory.IN_PROGRESS
            and item.updated_at is not None
            and excluded_labels.isdisjoint(item.labels)
        )

    def _finding(
        self,
        data: SignalData,
        ctx: EvaluationContext,
        item: WorkItem,
        days_idle: int,
        threshold: int,
    ) -> SignalFinding:
        assert item.updated_at is not None
        return SignalFinding(
            report_id=data.report_id,
            signal_id=self.id,
            signal_name=self.name,
            severity=self.default_severity,
            confidence=Confidence.HIGH,
            entity_type=EntityType.WORKITEM,
            entity_id=item.id,
            title=f"{item.key} stale for {days_idle} days",
            reason=f"{item.key} has had no update for {days_idle} days",
            recommendation="Review the item and update its status or next action.",
            evidence={
                "days_idle": days_idle,
                "last_updated_at": item.updated_at.isoformat(),
                "threshold": threshold,
            },
            source_link=item.source_url,
            created_at=ctx.now,
        )

