from __future__ import annotations
from collections.abc import Callable, Sequence
from .contracts import AnalysisOutput, ThreatSignal
from .model_adapters import FrameArray
from .model_runtime import ModelRuntimeAdapter

class ThreatModelAdapter(ModelRuntimeAdapter):
    def __init__(self, *, name, version, model_path, infer: Callable | None = None, parser: Callable | None = None, **kwargs):
        super().__init__(name=name, version=version, model_path=model_path, infer=infer, parser=parser, **kwargs)
    def detect(self, frame: FrameArray) -> tuple[ThreatSignal, ...]: return tuple(self._predict(frame))
    def analyze(self, frame: FrameArray) -> AnalysisOutput: return AnalysisOutput(threat_signals=self.detect(frame))
