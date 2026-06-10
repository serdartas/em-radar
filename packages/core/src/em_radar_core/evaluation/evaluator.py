from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from em_radar_core.models import EvaluationContext, SignalFinding
from em_radar_core.signals import SignalData, SignalRegistry, default_registry


@dataclass(frozen=True)
class SignalConfig:
    signal_id: str
    enabled: bool = True
    params: Mapping[str, object] = field(default_factory=dict)


class SignalEvaluator:
    def __init__(self, registry: SignalRegistry = default_registry) -> None:
        self._registry = registry

    def evaluate(
        self,
        data: SignalData,
        ctx: EvaluationContext,
        configs: Iterable[SignalConfig] | None = None,
    ) -> list[SignalFinding]:
        findings: list[SignalFinding] = []
        effective_configs = (
            configs
            if configs is not None
            else (SignalConfig(signal_id=signal_id) for signal_id in self._registry.ids())
        )
        for config in effective_configs:
            if not config.enabled:
                continue
            signal = self._registry.create(config.signal_id, config.params)
            findings.extend(signal.evaluate(data, ctx))
        return findings
