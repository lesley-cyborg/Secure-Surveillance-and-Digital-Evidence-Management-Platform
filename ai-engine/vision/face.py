from __future__ import annotations

from typing import Any, cast

import cv2

from detection.detector import FrameArray
from vision.schemas import FaceObservation


class OpenCVFaceDetector:
    """Deterministic, CPU-safe face detector backed by OpenCV Haar cascades."""

    def __init__(
        self,
        *,
        cascade_path: str | None = None,
        scale_factor: float = 1.1,
        minimum_neighbors: int = 5,
    ) -> None:
        if scale_factor <= 1:
            raise ValueError("scale_factor must be greater than 1")
        if minimum_neighbors < 0:
            raise ValueError("minimum_neighbors cannot be negative")
        cascade_constructor = getattr(cv2, "CascadeClassifier", None)
        if cascade_constructor is None:
            self._cascade: Any = None
        else:
            cascade_root = getattr(getattr(cv2, "data", None), "haarcascades", "")
            self._cascade = cascade_constructor(
                cascade_path
                or (cascade_root + "haarcascade_frontalface_default.xml")
            )
        self.scale_factor = scale_factor
        self.minimum_neighbors = minimum_neighbors

    @property
    def model(self) -> tuple[str, str]:
        return ("opencv-haar-face", cv2.__version__)

    @property
    def is_ready(self) -> bool:
        return self._cascade is not None and not self._cascade.empty()

    def detect(self, frame: FrameArray) -> tuple[FaceObservation, ...]:
        if not self.is_ready:
            raise RuntimeError("OpenCV face cascade is not available")
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cast(Any, self._cascade).detectMultiScale(
            gray,
            scaleFactor=self.scale_factor,
            minNeighbors=self.minimum_neighbors,
        )
        return tuple(
            FaceObservation(
                confidence=1.0,
                bounding_box={
                    "x_min": x / width,
                    "y_min": y / height,
                    "x_max": (x + w) / width,
                    "y_max": (y + h) / height,
                },
            )
            for x, y, w, h in faces
        )
