from __future__ import annotations

from typing import Protocol, runtime_checkable

from detection.detector import FrameArray
from vision.schemas import FaceObservation, OCRText


class OCRProviderError(RuntimeError):
    """An OCR runtime failure that should not fail image analysis."""


@runtime_checkable
class OCRProvider(Protocol):
    @property
    def model(self) -> tuple[str, str]: ...

    @property
    def is_ready(self) -> bool: ...

    def extract(self, frame: FrameArray) -> tuple[OCRText, ...]: ...


@runtime_checkable
class FaceDetector(Protocol):
    @property
    def model(self) -> tuple[str, str]: ...

    @property
    def is_ready(self) -> bool: ...

    def detect(self, frame: FrameArray) -> tuple[FaceObservation, ...]: ...
