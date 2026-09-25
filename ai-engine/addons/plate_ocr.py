from __future__ import annotations

import re
from typing import Protocol

import structlog

from addons.schemas import PlateCandidate, PlateObservation
from detection.detector import FrameArray

logger = structlog.get_logger(__name__)
_PLATE_TEXT_FILTER = re.compile(r"[^A-Z0-9]")
_NON_RESULT_TEXT = frozenset({"pending", "unreadable"})


class PlateOCRProvider(Protocol):
    @property
    def is_ready(self) -> bool: ...

    def read(self, crop: FrameArray) -> tuple[str, float]: ...


class TesseractPlateOCR:
    def __init__(self, *, language: str = "eng") -> None:
        self.language = language

    @property
    def is_ready(self) -> bool:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
        except (ImportError, OSError, RuntimeError):
            return False
        return True

    def read(self, crop: FrameArray) -> tuple[str, float]:
        try:
            import pytesseract
            from pytesseract import Output

            data = pytesseract.image_to_data(
                crop,
                lang=self.language,
                config="--psm 7",
                output_type=Output.DICT,
            )
        except ImportError as exception:
            raise RuntimeError("Tesseract OCR dependency is unavailable") from exception
        except (OSError, RuntimeError, pytesseract.TesseractError) as exception:
            raise RuntimeError("Tesseract OCR extraction failed") from exception
        recognized = "".join(str(value).strip() for value in data.get("text", ()))
        text = _PLATE_TEXT_FILTER.sub("", recognized.upper())
        confidences = [
            float(value) / 100
            for value in data.get("conf", ())
            if _is_numeric_confidence(value)
        ]
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        if not text or text.casefold() in _NON_RESULT_TEXT:
            return "", 0.0
        return text[:32], max(0.0, min(1.0, confidence))


def enrich_plate_candidates(
    frame: FrameArray,
    candidates: tuple[PlateCandidate, ...],
    ocr: PlateOCRProvider,
) -> tuple[PlateObservation, ...]:
    if not ocr.is_ready:
        raise RuntimeError("Tesseract OCR is unavailable")
    height, width = frame.shape[:2]
    observations: list[PlateObservation] = []
    for candidate in candidates:
        box = candidate.bounding_box
        x_min = max(0, min(width - 1, int(box.x_min * width)))
        y_min = max(0, min(height - 1, int(box.y_min * height)))
        x_max = max(x_min + 1, min(width, int(box.x_max * width)))
        y_max = max(y_min + 1, min(height, int(box.y_max * height)))
        crop = frame[y_min:y_max, x_min:x_max]
        if crop.size == 0:
            continue
        try:
            text, confidence = ocr.read(crop.copy())
        except Exception as exception:
            logger.warning(
                "plate_ocr_degraded",
                error_type=type(exception).__name__,
            )
            raise
        normalized_text = _PLATE_TEXT_FILTER.sub("", text.upper())
        if not normalized_text or normalized_text.casefold() in _NON_RESULT_TEXT:
            continue
        observations.append(
            PlateObservation(
                text=normalized_text[:32],
                confidence=max(0.0, min(1.0, confidence)),
                bounding_box=box,
            )
        )
    return tuple(observations)


def _is_numeric_confidence(value: object) -> bool:
    if hasattr(value, "item"):
        value = value.item()
    if not isinstance(value, (str, int, float)):
        return False
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False
