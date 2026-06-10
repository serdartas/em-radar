from collections.abc import Mapping

from em_radar_core.signals.base import Signal


class SignalRegistry:
    def __init__(self) -> None:
        self._signals: dict[str, type[Signal]] = {}

    def register(self, signal_type: type[Signal]) -> None:
        if signal_type.id in self._signals:
            raise ValueError(f"signal already registered: {signal_type.id}")
        self._signals[signal_type.id] = signal_type

    def create(self, signal_id: str, params: Mapping[str, object] | None = None) -> Signal:
        return self.get(signal_id)(params)

    def get(self, signal_id: str) -> type[Signal]:
        try:
            return self._signals[signal_id]
        except KeyError as error:
            raise KeyError(f"unknown signal: {signal_id}") from error

    def ids(self) -> tuple[str, ...]:
        return tuple(self._signals)
