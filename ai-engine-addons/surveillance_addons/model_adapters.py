from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
import numpy as np
from numpy.typing import NDArray
from .contracts import PlateObservation, PoseObservation, ThreatSignal

FrameArray = NDArray[np.uint8]

class ThreatDetector(Protocol):
    @property
    def is_ready(self) -> bool: ...
    def detect(self, frame: FrameArray) -> Sequence[ThreatSignal]: ...

class PlateAnalyzer(Protocol):
    @property
    def is_ready(self) -> bool: ...
    def detect(self, frame: FrameArray) -> Sequence[PlateObservation]: ...

class PoseDetector(Protocol):
    @property
    def is_ready(self) -> bool: ...
    def detect(self, frame: FrameArray) -> Sequence[PoseObservation]: ...
