from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

import numpy as np
import structlog
from numpy.typing import NDArray

from addons.plate_ocr import PlateOCRProvider, enrich_plate_candidates
from addons.pose_confirmation import PoseConfirmation
from addons.schemas import (
    AddonAnalysisResult,
    PlateCandidate,
    PlateObservation,
    PoseObservation,
    ThreatSignal,
)

FrameArray = NDArray[np.uint8]
logger = structlog.get_logger(__name__)


class _Detector(Protocol):
    @property
    def is_ready(self) -> bool: ...

    def detect(self, frame: FrameArray) -> Sequence[object]: ...


class AnalysisPipeline:
    def __init__(
        self,
        *,
        threat: _Detector | None = None,
        plates: _Detector | None = None,
        pose: _Detector | None = None,
        plate_ocr: PlateOCRProvider | None = None,
        pose_confirmation: PoseConfirmation | None = None,
    ) -> None:
        self._threat = threat
        self._plates = plates
        self._pose = pose
        self._plate_ocr = plate_ocr
        self._pose_confirmation = pose_confirmation or PoseConfirmation()

    async def analyze(
        self,
        frame: FrameArray,
        *,
        detections: Sequence[tuple[str, float]] = (),
        camera_id: str | None = None,
        sequence_number: int | None = None,
    ) -> AddonAnalysisResult:
        degraded: set[str] = set()
        jobs = [
            self._run_detector(name, detector, frame)
            for name, detector in (
                ("threat", self._threat),
                ("plates", self._plates),
                ("pose", self._pose),
            )
            if detector is not None
        ]
        results = await asyncio.gather(*jobs)
        by_capability: dict[str, tuple[object, ...]] = {}
        for name, values, failed in results:
            by_capability[name] = values
            if failed:
                degraded.add(name)

        signals = list(by_capability.get("threat", ()))
        # Canonical names only (parser normalizes weapon-detector output)
        known_threats = frozenset(  
            {"knife", "sword", "rifle", "pistol", "firearm", "weapon"} 
        )      
        signals.extend(
            ThreatSignal(
                signal=label.casefold().replace("","_"),
                confidence=confidence,
                source="object_detection",
            )
            for label, confidence in detections
            if label.casefold().replace(" ", "_") in known_threats
        )

        plate_candidates = tuple(
            value
            for value in by_capability.get("plates", ())
            if isinstance(value, PlateCandidate)
        )
        plates: tuple[PlateObservation, ...] = ()
        if plate_candidates:
            if self._plate_ocr is None:
                degraded.add("plate_ocr")
            else:
                try:
                    plates = await asyncio.to_thread(
                        enrich_plate_candidates,
                        frame,
                        plate_candidates,
                        self._plate_ocr,
                    )
                except Exception as exception:
                    logger.warning(
                        "plate_ocr_pipeline_degraded",
                        error_type=type(exception).__name__,
                    )
                    degraded.add("plate_ocr")

        poses = tuple(
            value
            for value in by_capability.get("pose", ())
            if isinstance(value, PoseObservation)
        )
        if poses and camera_id is not None and sequence_number is not None:
            poses = self._pose_confirmation.update(
                camera_id,
                sequence_number,
                poses,
            )
        else:
            poses = tuple(
                pose.model_copy(update={"confirmed": False})
                for pose in poses
            )

        return AddonAnalysisResult(
            threat_signals=tuple(
                value for value in signals if isinstance(value, ThreatSignal)
            ),
            weapon_count=sum(
                signal.signal.casefold().replace(" ", "_") in known_threats
                for signal in signals
                if isinstance(signal, ThreatSignal)
            ),
            plates=plates,
            poses=poses,
            degraded_capabilities=tuple(sorted(degraded)),
        )

    @staticmethod
    async def _run_detector(
        name: str,
        detector: _Detector,
        frame: FrameArray,
    ) -> tuple[str, tuple[object, ...], bool]:
        try:
            if not detector.is_ready:
                return name, (), True
            values = await asyncio.to_thread(detector.detect, frame)
            return name, tuple(values), False
        except Exception as exception:
            logger.warning(
                "addon_detection_degraded",
                capability=name,
                error_type=type(exception).__name__,
            )
            return name, (), True
