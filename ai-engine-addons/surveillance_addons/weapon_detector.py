from __future__ import annotations
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from .contracts import AnalysisOutput, ThreatSignal
from .model_adapters import FrameArray
@dataclass(slots=True)
class WeaponDetector:
    name: str
    version: str
    infer: Callable[[FrameArray], Sequence[ThreatSignal]]
    ready: bool = True
    @property
    def is_ready(self) -> bool: return self.ready
    def detect(self, frame: FrameArray) -> tuple[ThreatSignal,...]: return tuple(self.infer(frame))
    def analyze(self, frame: FrameArray) -> AnalysisOutput: return AnalysisOutput(threat_signals=self.detect(frame))
