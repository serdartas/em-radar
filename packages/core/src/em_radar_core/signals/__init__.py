from em_radar_core.signals.base import Signal, SignalData, SignalParams
from em_radar_core.signals.registry import SignalRegistry
from em_radar_core.signals.stale_in_progress import (
    StaleInProgressParams,
    StaleInProgressSignal,
)

default_registry = SignalRegistry()
default_registry.register(StaleInProgressSignal)

__all__ = [
    "Signal",
    "SignalData",
    "SignalParams",
    "SignalRegistry",
    "StaleInProgressParams",
    "StaleInProgressSignal",
    "default_registry",
]

