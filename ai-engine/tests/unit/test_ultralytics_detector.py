from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import (
    Self,
    cast,
)

import numpy as np
import pytest
from numpy.typing import NDArray

from detection.detector import FrameArray
from detection.exceptions import (
    ModelIntegrityError,
    ModelLoadError,
)
from detection.schemas import DeviceType
from models.ultralytics_detector import (
    PredictionModel,
    UltralyticsDetector,
)


class FakeTensor:
    def __init__(
        self,
        value: NDArray[np.float64],
    ) -> None:
        self._value = value

    def cpu(self) -> Self:
        return self

    def numpy(
        self,
    ) -> NDArray[np.float64]:
        return self._value


class FakeBoxes:
    def __init__(self) -> None:
        self.xyxy = FakeTensor(
            np.asarray(
                [
                    [10, 20, 100, 150],
                    [30, 40, 120, 160],
                ],
                dtype=np.float64,
            )
        )
        self.conf = FakeTensor(
            np.asarray(
                [0.95, 0.80],
                dtype=np.float64,
            )
        )
        self.cls = FakeTensor(
            np.asarray(
                [0, 1],
                dtype=np.float64,
            )
        )


class FakeResult:
    def __init__(self) -> None:
        self.boxes = FakeBoxes()


class FakePredictionModel:
    def __init__(self) -> None:
        self.names: Mapping[int, str] | Sequence[str] = {
            0: "person",
            1: "dog",
        }
        self.predict_calls = 0

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
        del source
        del imgsz
        del conf
        del iou
        del device
        del verbose

        self.predict_calls += 1

        return (FakeResult(),)


def _model_file(
    temporary_path: Path,
) -> Path:
    path = temporary_path / "model.pt"
    path.write_bytes(b"fake-model-data")
    return path


def _detector(
    model_path: Path,
    model: FakePredictionModel,
    *,
    expected_sha256: str | None = None,
) -> UltralyticsDetector:
    def model_loader(_: Path) -> PredictionModel:
        return model

    return UltralyticsDetector(
        model_path=model_path,
        model_name="test-detector",
        model_version="1.0.0",
        requested_device=DeviceType.CPU,
        cuda_device_index=0,
        image_size=640,
        backend_confidence_floor=0.001,
        iou_threshold=0.7,
        allowed_labels=("person",),
        expected_sha256=expected_sha256,
        model_loader=model_loader,
        cuda_probe=lambda: False,
    )


def test_detector_loads_and_reports_ready(
    tmp_path: Path,
) -> None:
    model = FakePredictionModel()

    detector = _detector(
        _model_file(tmp_path),
        model,
    )

    detector.load()

    assert detector.is_ready is True
    assert detector.identity.device is (DeviceType.CPU)
    assert detector.identity.labels == ("person",)


def test_detector_converts_and_filters_results(
    tmp_path: Path,
) -> None:
    model = FakePredictionModel()

    detector = _detector(
        _model_file(tmp_path),
        model,
    )
    detector.load()

    frame = cast(
        FrameArray,
        np.zeros(
            (200, 300, 3),
            dtype=np.uint8,
        ),
    )

    detections = detector.detect(frame)

    assert len(detections) == 1
    assert detections[0].label == "person"
    assert detections[0].confidence == (pytest.approx(0.95))
    assert detections[0].bounding_box.x_min == pytest.approx(10)


def test_detector_warmup_runs_prediction(
    tmp_path: Path,
) -> None:
    model = FakePredictionModel()

    detector = _detector(
        _model_file(tmp_path),
        model,
    )
    detector.load()

    detector.warm_up()

    assert model.predict_calls == 1


def test_detector_unload_clears_readiness(
    tmp_path: Path,
) -> None:
    model = FakePredictionModel()

    detector = _detector(
        _model_file(tmp_path),
        model,
    )
    detector.load()
    detector.unload()

    assert detector.is_ready is False


def test_detector_rejects_missing_model(
    tmp_path: Path,
) -> None:
    detector = _detector(
        tmp_path / "missing.pt",
        FakePredictionModel(),
    )

    with pytest.raises(ModelLoadError):
        detector.load()


def test_detector_rejects_checksum_mismatch(
    tmp_path: Path,
) -> None:
    path = _model_file(tmp_path)

    detector = _detector(
        path,
        FakePredictionModel(),
        expected_sha256="0" * 64,
    )

    with pytest.raises(ModelIntegrityError):
        detector.load()


def test_detector_accepts_valid_checksum(
    tmp_path: Path,
) -> None:
    path = _model_file(tmp_path)

    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    detector = _detector(
        path,
        FakePredictionModel(),
        expected_sha256=expected,
    )

    detector.load()

    assert detector.is_ready is True
