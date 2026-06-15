from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from em_radar_core.models import Severity


class CatalogParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StaleInProgressWorkItemParams(CatalogParams):
    days_threshold: int = 7
    exclude_labels: list[str] = Field(default_factory=list)


class BlockedWithoutUpdateParams(CatalogParams):
    days_threshold: int = 3


class NoParams(CatalogParams):
    pass


class EpicTooBroadParams(CatalogParams):
    max_children: int = 15


class EpicWithoutMeasurableDescriptionParams(CatalogParams):
    min_description_length: int = 100


class RepeatedCarryOverParams(CatalogParams):
    min_sprint_count: int = 2


class SprintScopeChurnParams(CatalogParams):
    warning_pct: float = 20.0
    critical_pct: float = 35.0


class MergeRequestWaitingTooLongParams(CatalogParams):
    days_threshold: int = 3


class MergeRequestWithoutLinkedWorkItemParams(CatalogParams):
    workitem_key_pattern: str = r"[A-Z]+-\d+"


class LargeMergeRequestRiskParams(CatalogParams):
    max_files: int = 20
    max_changes: int = 500


class FailingPipelineTooLongParams(CatalogParams):
    days_threshold: int = 1


class MergedWithoutEnoughApprovalParams(CatalogParams):
    min_approvals: int = 1


@dataclass(frozen=True)
class SignalCatalogEntry:
    id: str
    default_severity: Severity
    params_schema: type[CatalogParams]


SIGNAL_CATALOG = {
    entry.id: entry
    for entry in (
        SignalCatalogEntry(
            "stale-in-progress-work-item", Severity.WARNING, StaleInProgressWorkItemParams
        ),
        SignalCatalogEntry("blocked-without-update", Severity.CRITICAL, BlockedWithoutUpdateParams),
        SignalCatalogEntry("story-without-acceptance-criteria", Severity.WARNING, NoParams),
        SignalCatalogEntry("story-without-parent-epic", Severity.INFO, NoParams),
        SignalCatalogEntry("epic-too-broad", Severity.WARNING, EpicTooBroadParams),
        SignalCatalogEntry(
            "epic-without-measurable-description",
            Severity.INFO,
            EpicWithoutMeasurableDescriptionParams,
        ),
        SignalCatalogEntry("repeated-carry-over", Severity.WARNING, RepeatedCarryOverParams),
        SignalCatalogEntry("sprint-scope-churn", Severity.WARNING, SprintScopeChurnParams),
        SignalCatalogEntry(
            "mergerequest-waiting-too-long", Severity.WARNING, MergeRequestWaitingTooLongParams
        ),
        SignalCatalogEntry(
            "mergerequest-without-linked-workitem",
            Severity.WARNING,
            MergeRequestWithoutLinkedWorkItemParams,
        ),
        SignalCatalogEntry(
            "large-mergerequest-risk", Severity.WARNING, LargeMergeRequestRiskParams
        ),
        SignalCatalogEntry(
            "failing-pipeline-too-long", Severity.WARNING, FailingPipelineTooLongParams
        ),
        SignalCatalogEntry(
            "merged-without-enough-approval", Severity.CRITICAL, MergedWithoutEnoughApprovalParams
        ),
    )
}
