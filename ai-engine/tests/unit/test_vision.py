from __future__ import annotations

import numpy as np
import pytesseract
import pytest

from detection.detector import FrameArray
from vision.analysis import VisionAnalyzer
from vision.interfaces import OCRProviderError
from vision.ocr import TesseractOCR
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


class FailingOCR:
    model = ("fake-ocr", "1")
    is_ready = True

    def extract(self, frame: FrameArray) -> tuple[OCRText, ...]:
        del frame
        raise OCRProviderError("Tesseract runtime failed")


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


async def test_vision_analyzer_degrades_when_ocr_fails() -> None:
    result = await VisionAnalyzer(ocr=FailingOCR()).analyze(
        np.zeros((10, 10, 3), dtype=np.uint8),
    )

    assert result.ocr == ()
    assert result.ocr_model is None


def test_tesseract_ocr_returns_no_placeholder_for_blank_recognition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *args, **kwargs: {
            "text": [" "],
            "conf": ["-1"],
            "left": [0],
            "top": [0],
            "width": [0],
            "height": [0],
        },
    )

    result = TesseractOCR().extract(
        np.zeros((10, 10, 3), dtype=np.uint8),
    )

    assert result == ()


def test_tesseract_ocr_wraps_runtime_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise pytesseract.TesseractError(1, "Tesseract process failed")

    monkeypatch.setattr(pytesseract, "image_to_data", fail)

    with pytest.raises(OCRProviderError, match="extraction failed"):
        TesseractOCR().extract(
            np.zeros((10, 10, 3), dtype=np.uint8),
        )


async def test_vision_analyzer_does_not_classify_incidents() -> None:
    result = await VisionAnalyzer().analyze(
        np.zeros((10, 10, 3), dtype=np.uint8),
        detections=(("weapon", 0.99),),
    )

    assert result.threat_signals[0].signal == "weapon"
    assert not hasattr(result, "incident_type")
