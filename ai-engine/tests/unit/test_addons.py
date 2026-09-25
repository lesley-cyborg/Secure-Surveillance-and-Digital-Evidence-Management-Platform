from __future__ import annotations

import hashlib
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

import addons.model_adapter as model_adapter
from addons.model_adapter import UltralyticsAddonModel
from addons.pipeline import AnalysisPipeline
from addons.plate_ocr import enrich_plate_candidates
from addons.pose_confirmation import PoseConfirmation
from addons.schemas import (
    BoundingBox,
    PlateCandidate,
    PlateObservation,
    PoseObservation,
)
from detection.schemas import DeviceType


def _pose(confidence: float = 0.9) -> PoseObservation:
    return PoseObservation(
        posture="person",
        confidence=confidence,
        bounding_box=BoundingBox(
            x_min=0.1,
            y_min=0.1,
            x_max=0.5,
            y_max=0.8,
        ),
    )


def test_pose_confirmation_requires_repeated_matched_observations() -> None:
    confirmer = PoseConfirmation(required_frames=2)

    first = confirmer.update("camera-1", 1, (_pose(),), now=1.0)
    second = confirmer.update("camera-1", 2, (_pose(),), now=2.0)

    assert first[0].confirmed is False
    assert second[0].confirmed is True
    assert not hasattr(second[0], "track_id")


def test_pose_confirmation_is_camera_scoped_and_resets_on_sequence_restart() -> None:
    confirmer = PoseConfirmation(required_frames=2)
    confirmer.update("camera-1", 10, (_pose(),), now=1.0)

    other_camera = confirmer.update("camera-2", 11, (_pose(),), now=2.0)
    restarted = confirmer.update("camera-1", 0, (_pose(),), now=3.0)

    assert other_camera[0].confirmed is False
    assert restarted[0].confirmed is False


def test_pose_confirmation_rejects_low_confidence_sample() -> None:
    confirmer = PoseConfirmation(required_frames=2)
    confirmer.update("camera-1", 1, (_pose(),), now=1.0)

    low = confirmer.update("camera-1", 2, (_pose(0.2),), now=2.0)
    next_sample = confirmer.update("camera-1", 3, (_pose(),), now=3.0)

    assert low[0].confirmed is False
    assert next_sample[0].confirmed is False


def test_unreadable_plate_ocr_never_emits_placeholder() -> None:
    class UnreadableOCR:
        @property
        def is_ready(self) -> bool:
            return True

        def read(self, crop: np.ndarray) -> tuple[str, float]:
            del crop
            return "unreadable", 0.0

    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    candidates = (
        PlateCandidate(
            confidence=0.9,
            bounding_box=BoundingBox(
                x_min=0.1,
                y_min=0.1,
                x_max=0.5,
                y_max=0.4,
            ),
        ),
    )

    assert enrich_plate_candidates(frame, candidates, UnreadableOCR()) == ()


@pytest.mark.asyncio
async def test_unavailable_plate_ocr_degrades_without_plate_text() -> None:
    class PlateDetector:
        @property
        def is_ready(self) -> bool:
            return True

        def detect(self, frame: np.ndarray) -> tuple[PlateCandidate, ...]:
            del frame
            return (
                PlateCandidate(
                    confidence=0.9,
                    bounding_box=BoundingBox(
                        x_min=0.1,
                        y_min=0.1,
                        x_max=0.5,
                        y_max=0.4,
                    ),
                ),
            )

    class UnreadyOCR:
        @property
        def is_ready(self) -> bool:
            return False

        def read(self, crop: np.ndarray) -> tuple[str, float]:
            del crop
            raise AssertionError("unready OCR must not be called")

    result = await AnalysisPipeline(
        plates=PlateDetector(),
        plate_ocr=UnreadyOCR(),
    ).analyze(np.zeros((100, 200, 3), dtype=np.uint8))

    assert result.plates == ()
    assert result.degraded_capabilities == ("plate_ocr",)


def test_plate_observation_rejects_pending_placeholder() -> None:
    with pytest.raises(ValueError, match="recognized"):
        PlateObservation(
            text="pending",
            confidence=0.0,
            bounding_box=BoundingBox(
                x_min=0.1,
                y_min=0.1,
                x_max=0.5,
                y_max=0.4,
            ),
        )


def test_addon_model_checks_digest_before_ultralytics_import(
    tmp_path: Path,
) -> None:
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"test weights")
    model = UltralyticsAddonModel(
        model_path=weights,
        expected_sha256="0" * 64,
        requested_device=DeviceType.CPU,
        cuda_device_index=0,
        task="threat",
    )

    with pytest.raises(ValueError, match="checksum"):
        model.load()

    assert model.is_ready is False


def test_addon_model_auto_device_uses_detected_cuda(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"test weights")
    prediction_devices: list[str | int] = []

    class FakeYOLO:
        def __init__(self, path: str) -> None:
            assert path == str(weights)

        def predict(
            self,
            *,
            source: np.ndarray,
            device: str | int,
            verbose: bool,
        ) -> list[object]:
            del source
            assert verbose is False
            prediction_devices.append(device)
            return []

    fake_ultralytics = ModuleType("ultralytics")
    fake_ultralytics.YOLO = FakeYOLO  # type: ignore[attr-defined]
    monkeypatch.setattr(
        model_adapter,
        "is_cuda_available",
        lambda: True,
    )
    monkeypatch.setattr(
        model_adapter.importlib,
        "import_module",
        lambda name: fake_ultralytics
        if name == "ultralytics"
        else pytest.fail(f"unexpected import: {name}"),
    )
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    model = UltralyticsAddonModel(
        model_path=weights,
        expected_sha256=digest,
        requested_device=DeviceType.AUTO,
        cuda_device_index=2,
        task="threat",
    )

    model.load()
    assert model.detect(np.zeros((1, 1, 3), dtype=np.uint8)) == ()
    assert prediction_devices == [2]
