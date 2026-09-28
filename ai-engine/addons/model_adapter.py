from __future__ import annotations

import hashlib
import importlib
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Any

from addons.parsers import (
    parse_plate_predictions,
    parse_pose_predictions,
    parse_threat_predictions,
)
from addons.schemas import PlateCandidate, PoseObservation, ThreatSignal
from detection.device import is_cuda_available, select_device
from detection.schemas import DeviceType


class UltralyticsAddonModel:
    """Local-only, checksum-validated Ultralytics model for one add-on task."""

    def __init__(
        self,
        *,
        model_path: Path,
        expected_sha256: str,
        requested_device: DeviceType,
        cuda_device_index: int,
        task: str,
    ) -> None:
        self.model_path = model_path
        self.expected_sha256 = expected_sha256.casefold()
        self.requested_device = requested_device
        self.cuda_device_index = cuda_device_index
        self.task = task
        self._model: Any = None
        self._device: str | int | None = None
        self._lock = RLock()

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            self._validate_weights()
            selected = select_device(
                self.requested_device,
                cuda_probe=is_cuda_available,
            )
            runtime_device: str | int = (
                self.cuda_device_index if selected is DeviceType.CUDA else "cpu"
            )
            try:
                ultralytics = importlib.import_module("ultralytics")
            except ImportError as exception:
                raise RuntimeError(
                    "Ultralytics is required for enabled add-on models"
                ) from exception
            yolo = getattr(ultralytics, "YOLO", None)
            if yolo is None:
                raise RuntimeError("Installed Ultralytics package does not expose YOLO")
            self._model = yolo(str(self.model_path))
            self._device = runtime_device

    def detect(
        self,
        frame: Any,
    ) -> (
        tuple[ThreatSignal, ...]
        | tuple[PlateCandidate, ...]
        | tuple[PoseObservation, ...]
    ):
        with self._lock:
            if self._model is None or self._device is None:
                raise RuntimeError("add-on model is not ready")
            results = self._model.predict(
                source=frame,
                device=self._device,
                verbose=False,
            )
            parser: Callable[[object], Any]
            if self.task == "threat":
                parser = parse_threat_predictions
            elif self.task == "plates":
                parser = parse_plate_predictions
            elif self.task == "pose":
                parser = parse_pose_predictions
            else:
                raise ValueError(f"Unsupported add-on model task: {self.task}")
            return parser(results)

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._device = None

    def _validate_weights(self) -> None:
        if not self.model_path.is_file() or self.model_path.stat().st_size <= 0:
            raise FileNotFoundError("Enabled add-on weights are missing or empty")
        actual = hashlib.sha256()
        with self.model_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                actual.update(chunk)
        if actual.hexdigest() != self.expected_sha256:
            raise ValueError("Enabled add-on model checksum does not match")
