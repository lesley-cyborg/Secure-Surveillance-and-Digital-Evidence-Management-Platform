from __future__ import annotations

import asyncio

import structlog

from detection.detector import FrameArray
from vision.interfaces import FaceDetector, OCRProvider, OCRProviderError
from vision.schemas import OCRText, ThreatSignal, VisionAnalysisResult, VisionModel

logger = structlog.get_logger(__name__)


class VisionAnalyzer:
    def __init__(
        self,
        *,
        ocr: OCRProvider | None = None,
        face_detector: FaceDetector | None = None,
        threat_labels: frozenset[str] = frozenset(
            {
                "weapon",
                "firearm",
                "gun",
                "knife",
                "sword",
                "pistol",
                "handgun",
                "rifle",
                "fire",
                "smoke",
                "violence",
            }
        ),
    ) -> None:
        self.ocr = ocr
        self.face_detector = face_detector
        self.threat_labels = threat_labels

    async def analyze(
        self,
        frame: FrameArray,
        *,
        detections: tuple[tuple[str, float], ...] = (),
    ) -> VisionAnalysisResult:
        ocr: tuple[OCRText, ...] = ()
        ocr_model = None
        if self.ocr is not None and self.ocr.is_ready:
            try:
                ocr = await asyncio.to_thread(self.ocr.extract, frame)
                ocr_model = VisionModel(
                    name=self.ocr.model[0],
                    version=self.ocr.model[1],
                )
            except OCRProviderError as exception:
                logger.warning(
                    "ocr_analysis_degraded",
                    error_type=type(exception).__name__,
                )

        faces = (
            await asyncio.to_thread(self.face_detector.detect, frame)
            if self.face_detector is not None and self.face_detector.is_ready
            else ()
        )
        signals = tuple(
            ThreatSignal(signal=label, confidence=confidence, source="object_detection")
            for label, confidence in detections
            if label.casefold().replace(" ", "_") in self.threat_labels
        )
        return VisionAnalysisResult(
            ocr=ocr,
            faces=faces,
            threat_signals=signals,
            plates=(),
            poses=(),
            weapon_count=0,
            degraded_capabilities=(),
            ocr_model=ocr_model,
            face_model=(
                VisionModel(
                    name=self.face_detector.model[0],
                    version=self.face_detector.model[1],
                )
                if self.face_detector is not None and self.face_detector.is_ready
                else None
            ),
        )
