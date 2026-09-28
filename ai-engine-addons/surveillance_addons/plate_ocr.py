from __future__ import annotations
from typing import Protocol
from .model_runtime import FrameArray

class PlateOCR(Protocol):
    @property 
    def is_ready(self) -> bool: ...
    def read(self, crop: FrameArray) -> tuple[str, float]: ...

class CallablePlateOCR:
    def __init__ (self, reader, *, ready: bool = True) -> None:
        self._reader = reader
        self._ready = ready
        @property
        def is_ready(self) -> bool: return self._ready
        def read(self, crop: FrameArray) -> tuple[str, float]: return self._reader(crop)
        