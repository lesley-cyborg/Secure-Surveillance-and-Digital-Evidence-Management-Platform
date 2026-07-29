from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from detection.schemas import (
    ModelIdentity,
    RawDetection,
)

type FrameArray = NDArray[np.uint8]


@runtime_checkable
class Detector(Protocol):
    """
    Model-independent object-detection contract.

    Implementations may use PyTorch, ONNX Runtime, TensorRT,
    OpenVINO, or another inference runtime.
    """

    @property
    def identity(
        self,
    ) -> ModelIdentity:
        """Return immutable model metadata."""
        ...

    @property
    def is_ready(
        self,
    ) -> bool:
        """Return whether the model is available for inference."""
        ...

    def detect(
        self,
        frame: FrameArray,
    ) -> tuple[RawDetection, ...]:
        """
        Run inference against one BGR image frame.

        Pixel-coordinate detections are normalised later by the
        frame processor.
        """
        ...
