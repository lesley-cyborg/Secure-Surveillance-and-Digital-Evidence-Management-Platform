from __future__ import annotations
from collections.abc import Callable
from .contracts import AnalysisOutput, PlateObservation
from .model_adapters import FrameArray
from .model_runtime import ModelRuntimeAdapter

class PlateModelAdapter(ModelRuntimeAdapter):
    def __init__(self, *, name, version, model_path, infer: Callable | None = None, parser: Callable | None = None, **kwargs):
        super().__init__(name=name, version=version, model_path=model_path, infer=infer, parser=parser, **kwargs)
        def detect(self, frame: FrameArray) -> tuple[PlateObservation, ...]: return tuple(self._predict(frame))
        def analyze(self, frame: FrameArray )-> AnalysisOutput: return AnalysisOutput(plates=self.detect(frame))
