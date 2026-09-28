from __future__ import annotations
from dataclasses import dataclass    
from pathlib import Path    
from typing import Protocol    
from .contracts import AnalysisOutput
from .model_adapters import FrameArray
    
@dataclass(frozen=True, slots=True)    
class ModelIdentity:
    name: str
    version: str
    path: Path
    device: str
    
class AnalysisMode(Prototcol):    
    @property
    def identity(self) -> ModelIdentity: ...
    @property
    def is_ready(self) -> bool: ...
    def load(self) -> None: ...
    def warm_up(self) -> None: ...
    def unload(self) -> None: ...
    def analyze(self, frame: FrameArray) -> AnalysisOutput: ...
    