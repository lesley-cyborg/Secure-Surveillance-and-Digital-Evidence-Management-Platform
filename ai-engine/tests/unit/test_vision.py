from __future__ import annotations

import numpy as np

from detection.detector import FrameArray
from vision.analysis import VisionAnalyzer
from vision.schemas import FaceObservation, OCRText


class FakeOCR:
    model = ("fake-ocr", "1")
    is_ready = True

    def extract(self, frame: FrameArray) -> tuple[OCRText, ...]:
        del frame
        return (OCRText(text="CASE 123", confidence=0.91),)


class FakeFaces:
    model = ("fake-face", "1")
    is_ready = True

    def detect(self, frame: FrameArray) -> tuple[FaceObservation, ...]:
        del frame
        return (
            FaceObservation(
                confidence=0.88,
                bounding_box={
                    "x_min": 0.1,
                    "y_min": 0.2,
                    "x_max": 0.3,
                    "y_max": 0.5,
                },
            ),
        )


async def test_vision_analyzer_returns_enrichments_and_signals() -> None:
    result = await VisionAnalyzer(
        ocr=FakeOCR(),
        face_detector=FakeFaces(),
    ).analyze(
        np.zeros((100, 200, 3), dtype=np.uint8),
        detections=(("weapon", 0.8), ("person", 0.99)),
    )

    assert result.ocr[0].text == "CASE 123"
    assert len(result.faces) == 1
    assert result.threat_signals[0].signal == "weapon"
    assert result.threat_signals[0].source == "object_detection"


async def test_vision_analyzer_does_not_classify_incidents() -> None:
    result = await VisionAnalyzer().analyze(
        np.zeros((10, 10, 3), dtype=np.uint8),
        detections=(("weapon", 0.99),),
    )

    assert result.threat_signals[0].signal == "weapon"
    assert not hasattr(result, "incident_type")
