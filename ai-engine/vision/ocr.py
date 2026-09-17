from __future__ import annotations

from detection.detector import FrameArray
from vision.schemas import OCRText


class TesseractOCR:
    """OCR adapter using the locally installed Tesseract executable."""

    def __init__(
        self,
        *,
        language: str = "eng",
        minimum_confidence: float = 0.0,
    ) -> None:
        if not language.strip():
            raise ValueError("language cannot be empty")
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")
        self.language = language
        self.minimum_confidence = minimum_confidence

    @property
    def model(self) -> tuple[str, str]:
        return ("tesseract", "5")

    @property
    def is_ready(self) -> bool:
        try:
            import pytesseract  # type: ignore[import-untyped]

            pytesseract.get_tesseract_version()
        except (ImportError, OSError, RuntimeError):
            return False
        return True

    def extract(self, frame: FrameArray) -> tuple[OCRText, ...]:
        import pytesseract
        from pytesseract import Output

        data = pytesseract.image_to_data(
            frame,
            lang=self.language,
            output_type=Output.DICT,
        )
        height, width = frame.shape[:2]
        results: list[OCRText] = []
        for index, raw_text in enumerate(data["text"]):
            text = raw_text.strip()
            confidence = float(data["conf"][index]) / 100
            if not text or confidence < self.minimum_confidence:
                continue
            x, y = data["left"][index], data["top"][index]
            box_width, box_height = data["width"][index], data["height"][index]
            results.append(
                OCRText(
                    text=text,
                    confidence=max(0.0, min(1.0, confidence)),
                    bounding_box={
                        "x_min": x / width,
                        "y_min": y / height,
                        "x_max": (x + box_width) / width,
                        "y_max": (y + box_height) / height,
                    },
                )
            )
        return tuple(results)
