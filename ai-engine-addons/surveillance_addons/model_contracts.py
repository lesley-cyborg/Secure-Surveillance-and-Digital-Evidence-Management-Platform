from __future__ import annotations
from collections.abc import Sequence
from typing import Protocol
from .contracts import AnalysisOutput
from .model_adapters import FrameArray

class ModelIdentity(Protocol):
    name: str
    version: str
    device: str

class AnalysisModel(Protocol):
    @property
    def identity(self) -> ModelIdentity: ...
    @property
    def is_ready(self) -> bool: ...
    def load(self) -> None: ...
    def warm_up(self) -> None: ...
    def unload(self) -> None: ...
    def analyze(self, frame: FrameArray) -> AnalysisOutput: ...
