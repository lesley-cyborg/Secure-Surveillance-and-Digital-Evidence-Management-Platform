from __future__ import annotations

import asyncio

from detection.detector import FrameArray
from vision.interfaces import FaceDetector, OCRProvider
from vision.schemas import ThreatSignal, VisionAnalysisResult, VisionModel


class VisionAnalyzer:
    def __init__(
        self,
        *,
        ocr: OCRProvider | None = None,
        face_detector: FaceDetector | None = None,
        threat_labels: frozenset[str] = frozenset(
            {"weapon", "firearm", "gun", "knife", "fire", "smoke", "violence"}
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
        ocr = (
            await asyncio.to_thread(self.ocr.extract, frame)
            if self.ocr is not None and self.ocr.is_ready
            else ()
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
            ocr_model=VisionModel(name=self.ocr.model[0], version=self.ocr.model[1])
            if self.ocr is not None and self.ocr.is_ready
            else None,
            face_model=(
                VisionModel(
                    name=self.face_detector.model[0],
                    version=self.face_detector.model[1],
                )
            )
            if self.face_detector is not None and self.face_detector.is_ready
            else None,
        )
