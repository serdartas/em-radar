from em_radar_core.signals.base import Signal, SignalData, SignalParams
from em_radar_core.signals.registry import SignalRegistry
from em_radar_core.signals.sprints import (
    SprintScopeChurnParams,
    SprintScopeChurnSignal,
)
from em_radar_core.signals.stale_in_progress import (
    StaleInProgressParams,
    StaleInProgressSignal,
)
from em_radar_core.signals.workitems import (
    BlockedWithoutUpdateParams,
    BlockedWithoutUpdateSignal,
    EpicTooBroadParams,
    EpicTooBroadSignal,
    EpicWithoutMeasurableDescriptionParams,
    EpicWithoutMeasurableDescriptionSignal,
    RepeatedCarryOverParams,
    RepeatedCarryOverSignal,
    StoryWithoutAcceptanceCriteriaParams,
    StoryWithoutAcceptanceCriteriaSignal,
    StoryWithoutParentEpicParams,
    StoryWithoutParentEpicSignal,
)

default_registry = SignalRegistry()
default_registry.register(StaleInProgressSignal)
default_registry.register(BlockedWithoutUpdateSignal)
default_registry.register(StoryWithoutAcceptanceCriteriaSignal)
default_registry.register(StoryWithoutParentEpicSignal)
default_registry.register(EpicTooBroadSignal)
default_registry.register(EpicWithoutMeasurableDescriptionSignal)
default_registry.register(RepeatedCarryOverSignal)
default_registry.register(SprintScopeChurnSignal)

__all__ = [
    "BlockedWithoutUpdateParams",
    "BlockedWithoutUpdateSignal",
    "EpicTooBroadParams",
    "EpicTooBroadSignal",
    "EpicWithoutMeasurableDescriptionParams",
    "EpicWithoutMeasurableDescriptionSignal",
    "RepeatedCarryOverParams",
    "RepeatedCarryOverSignal",
    "Signal",
    "SignalData",
    "SignalParams",
    "SignalRegistry",
    "SprintScopeChurnParams",
    "SprintScopeChurnSignal",
    "StaleInProgressParams",
    "StaleInProgressSignal",
    "StoryWithoutAcceptanceCriteriaParams",
    "StoryWithoutAcceptanceCriteriaSignal",
    "StoryWithoutParentEpicParams",
    "StoryWithoutParentEpicSignal",
    "default_registry",
]
