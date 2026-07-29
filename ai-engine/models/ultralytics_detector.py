from __future__ import annotations

import hashlib
import importlib
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)
from pathlib import Path
from threading import RLock
from typing import Protocol, cast

import numpy as np
import structlog
from numpy.typing import NDArray

from detection.detector import FrameArray
from detection.device import (
    CudaAvailabilityProbe,
    is_cuda_available,
    select_device,
)
from detection.exceptions import (
    DetectionEngineError,
    DetectorUnavailableError,
    InferenceError,
    ModelIntegrityError,
    ModelLoadError,
)
from detection.schemas import (
    DeviceType,
    ModelIdentity,
    PixelBoundingBox,
    RawDetection,
)

logger = structlog.get_logger(__name__)


class PredictionModel(Protocol):
    names: Mapping[int, str] | Sequence[str]

    def predict(
        self,
        *,
        source: FrameArray,
        imgsz: int,
        conf: float,
        iou: float,
        device: str | int,
        verbose: bool,
    ) -> Sequence[object]:
        """Run one object-detection prediction."""
        ...


type ModelLoader = Callable[
    [Path],
    PredictionModel,
]


def default_model_loader(
    model_path: Path,
) -> PredictionModel:
    try:
        module = importlib.import_module("ultralytics")
    except ImportError as exception:
        raise ModelLoadError(
            "Ultralytics is not installed. Install the model dependency group."
        ) from exception

    yolo_class = getattr(
        module,
        "YOLO",
        None,
    )

    if yolo_class is None:
        raise ModelLoadError("The installed Ultralytics package does not expose YOLO")

    try:
        model = yolo_class(str(model_path))
    except Exception as exception:
        raise ModelLoadError(
            f"Ultralytics could not load the model: {model_path}"
        ) from exception

    return cast(
        PredictionModel,
        model,
    )


class UltralyticsDetector:
    """
    Production adapter for an Ultralytics detection model.

    The adapter requires a local model file. It never initiates
    a model download during application startup.
    """

    def __init__(
        self,
        *,
        model_path: Path,
        model_name: str,
        model_version: str,
        requested_device: DeviceType,
        cuda_device_index: int,
        image_size: int,
        backend_confidence_floor: float,
        iou_threshold: float,
        allowed_labels: tuple[str, ...],
        expected_sha256: str | None = None,
        model_loader: ModelLoader = (default_model_loader),
        cuda_probe: CudaAvailabilityProbe = (is_cuda_available),
    ) -> None:
        if image_size <= 0:
            raise ValueError("image_size must be positive")

        if not (0 <= backend_confidence_floor <= 1):
            raise ValueError("backend_confidence_floor must be between 0 and 1")

        if not 0 <= iou_threshold <= 1:
            raise ValueError("iou_threshold must be between 0 and 1")

        if cuda_device_index < 0:
            raise ValueError("cuda_device_index cannot be negative")

        self._model_path = model_path
        self._model_name = model_name
        self._model_version = model_version
        self._requested_device = requested_device
        self._cuda_device_index = cuda_device_index
        self._image_size = image_size
        self._backend_confidence_floor = backend_confidence_floor
        self._iou_threshold = iou_threshold
        self._expected_sha256 = expected_sha256.casefold() if expected_sha256 else None

        self._configured_labels = tuple(
            label.strip() for label in allowed_labels if label.strip()
        )
        self._allowed_label_keys = {
            label.casefold() for label in self._configured_labels
        }

        self._model_loader = model_loader
        self._cuda_probe = cuda_probe

        self._model: PredictionModel | None = None
        self._selected_device: DeviceType | None = None
        self._class_names: dict[int, str] = {}
        self._active_labels: tuple[str, ...] = self._configured_labels

        self._lock = RLock()

    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(
            name=self._model_name,
            version=self._model_version,
            device=(self._selected_device or self._requested_device),
            labels=self._active_labels,
        )

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._model is not None

    @property
    def model_path(self) -> Path:
        return self._model_path

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return

            self._validate_model_file()

            selected_device = select_device(
                self._requested_device,
                cuda_probe=self._cuda_probe,
            )

            try:
                model = self._model_loader(self._model_path)

                class_names = self._normalise_class_names(model.names)

                active_labels = self._resolve_active_labels(class_names)
            except DetectionEngineError:
                raise
            except Exception as exception:
                raise ModelLoadError(
                    "Unexpected failure while loading the production model"
                ) from exception

            self._model = model
            self._selected_device = selected_device
            self._class_names = class_names
            self._active_labels = active_labels

            logger.info(
                "production_model_loaded",
                model_name=self._model_name,
                model_version=(self._model_version),
                model_path=str(self._model_path),
                device=selected_device.value,
                labels=active_labels,
            )

    def warm_up(self) -> None:
        if not self.is_ready:
            raise DetectorUnavailableError(
                "The production model must be loaded before warm-up"
            )

        frame = cast(
            FrameArray,
            np.zeros(
                (
                    self._image_size,
                    self._image_size,
                    3,
                ),
                dtype=np.uint8,
            ),
        )

        self.detect(frame)

        logger.info(
            "production_model_warmed",
            model_name=self._model_name,
            model_version=self._model_version,
            image_size=self._image_size,
        )

    def detect(
        self,
        frame: FrameArray,
    ) -> tuple[RawDetection, ...]:
        with self._lock:
            model = self._model
            selected_device = self._selected_device

            if model is None or selected_device is None:
                raise DetectorUnavailableError("The production model is not loaded")

            runtime_device: str | int = (
                self._cuda_device_index if selected_device is DeviceType.CUDA else "cpu"
            )

            try:
                results = model.predict(
                    source=frame,
                    imgsz=self._image_size,
                    conf=(self._backend_confidence_floor),
                    iou=self._iou_threshold,
                    device=runtime_device,
                    verbose=False,
                )

                return self._convert_results(
                    results,
                    frame=frame,
                )
            except DetectionEngineError:
                raise
            except Exception as exception:
                raise InferenceError("Production model inference failed") from exception

    def unload(self) -> None:
        """Release detector references without expensive process-exit."""

        with self._lock:
            loaded_model = self._model

            self._model = None
            self._ready = False

        # Release the local reference after leaving the lock.
        del loaded_model

        # Preserve your existing CUDA-only cache cleanup.
        # if self._resolved_device.startswith("cuda"):
        #     torch.cuda.empty_cache()

        logger.info(
            "production_model_unloaded",
            model_name=self.identity.name,
            model_version=self.identity.version,
        )

    def _validate_model_file(self) -> None:
        if not self._model_path.exists():
            raise ModelLoadError(
                f"Production model file does not exist: {self._model_path}"
            )

        if not self._model_path.is_file():
            raise ModelLoadError(
                f"Production model path is not a file: {self._model_path}"
            )

        if self._model_path.stat().st_size <= 0:
            raise ModelLoadError("Production model file is empty")

        if self._expected_sha256 is None:
            return

        actual_sha256 = self._calculate_sha256(self._model_path)

        if actual_sha256 != self._expected_sha256:
            raise ModelIntegrityError(
                "Production model checksum does not match the configured SHA-256 digest"
            )

    def _resolve_active_labels(
        self,
        class_names: Mapping[int, str],
    ) -> tuple[str, ...]:
        available_labels = tuple(dict.fromkeys(class_names.values()))

        if not self._allowed_label_keys:
            return available_labels

        selected = tuple(
            label
            for label in available_labels
            if label.casefold() in self._allowed_label_keys
        )

        if not selected:
            raise ModelLoadError(
                "None of the configured labels exist in the selected model"
            )

        return selected

    def _convert_results(
        self,
        results: Sequence[object],
        *,
        frame: FrameArray,
    ) -> tuple[RawDetection, ...]:
        if not results:
            return ()

        result = results[0]
        boxes = getattr(
            result,
            "boxes",
            None,
        )

        if boxes is None:
            return ()

        xyxy = self._to_numpy(
            getattr(boxes, "xyxy", None),
            field_name="xyxy",
        )
        confidences = self._to_numpy(
            getattr(boxes, "conf", None),
            field_name="confidence",
        ).reshape(-1)
        classes = self._to_numpy(
            getattr(boxes, "cls", None),
            field_name="class",
        ).reshape(-1)

        if xyxy.ndim != 2 or xyxy.shape[1] != 4:
            raise InferenceError("Model returned invalid bounding-box dimensions")

        detection_count = xyxy.shape[0]

        if (
            confidences.shape[0] != detection_count
            or classes.shape[0] != detection_count
        ):
            raise InferenceError("Model output arrays have different detection counts")

        frame_height, frame_width = frame.shape[:2]

        detections: list[RawDetection] = []

        for index in range(detection_count):
            class_id = int(classes[index])
            label = self._class_names.get(class_id)

            if label is None:
                continue

            if (
                self._allowed_label_keys
                and label.casefold() not in self._allowed_label_keys
            ):
                continue

            confidence = float(confidences[index])

            raw_coordinates = xyxy[index]

            x_min = max(
                0.0,
                min(
                    float(raw_coordinates[0]),
                    float(frame_width),
                ),
            )
            y_min = max(
                0.0,
                min(
                    float(raw_coordinates[1]),
                    float(frame_height),
                ),
            )
            x_max = max(
                0.0,
                min(
                    float(raw_coordinates[2]),
                    float(frame_width),
                ),
            )
            y_max = max(
                0.0,
                min(
                    float(raw_coordinates[3]),
                    float(frame_height),
                ),
            )

            if x_max <= x_min or y_max <= y_min:
                continue

            detections.append(
                RawDetection(
                    class_id=class_id,
                    label=label,
                    confidence=confidence,
                    bounding_box=(
                        PixelBoundingBox(
                            x_min=x_min,
                            y_min=y_min,
                            x_max=x_max,
                            y_max=y_max,
                        )
                    ),
                )
            )

        return tuple(detections)

    @staticmethod
    def _normalise_class_names(
        names: Mapping[int, str] | Sequence[str],
    ) -> dict[int, str]:
        if isinstance(names, Mapping):
            return {int(class_id): str(label) for class_id, label in names.items()}

        return {class_id: str(label) for class_id, label in enumerate(names)}

    @staticmethod
    def _to_numpy(
        value: object,
        *,
        field_name: str,
    ) -> NDArray[np.float64]:
        if value is None:
            raise InferenceError(f"Model result is missing {field_name} data")

        current = value

        cpu_method = getattr(
            current,
            "cpu",
            None,
        )

        if callable(cpu_method):
            current = cpu_method()

        numpy_method = getattr(
            current,
            "numpy",
            None,
        )

        if callable(numpy_method):
            current = numpy_method()

        return np.asarray(
            current,
            dtype=np.float64,
        )

    @staticmethod
    def _calculate_sha256(
        path: Path,
    ) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as model_file:
            while chunk := model_file.read(1024 * 1024):
                digest.update(chunk)

        return digest.hexdigest()

    @staticmethod
    def _empty_cuda_cache() -> None:
        try:
            torch = importlib.import_module("torch")
            cuda = getattr(
                torch,
                "cuda",
                None,
            )
            empty_cache = getattr(
                cuda,
                "empty_cache",
                None,
            )

            if callable(empty_cache):
                empty_cache()
        except ImportError:
            return
