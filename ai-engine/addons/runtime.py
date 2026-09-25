from __future__ import annotations

import structlog

from addons.model_adapter import UltralyticsAddonModel
from addons.pipeline import AnalysisPipeline
from addons.plate_ocr import TesseractPlateOCR
from addons.pose_confirmation import PoseConfirmation
from config.settings import Settings

logger = structlog.get_logger(__name__)


class AddonRuntime:
    def __init__(
        self,
        *,
        pipeline: AnalysisPipeline,
        models: dict[str, UltralyticsAddonModel],
    ) -> None:
        self.pipeline = pipeline
        self.models = models
        self.degraded_capabilities: tuple[str, ...] = ()

    def startup(self) -> None:
        degraded: set[str] = set()
        for capability, model in self.models.items():
            try:
                model.load()
            except Exception as exception:
                degraded.add(capability)
                logger.warning(
                    "addon_model_startup_degraded",
                    capability=capability,
                    error_type=type(exception).__name__,
                )
        self.degraded_capabilities = tuple(sorted(degraded))

    def shutdown(self) -> None:
        for model in self.models.values():
            model.unload()


def build_addon_runtime(settings: Settings) -> AddonRuntime:
    models: dict[str, UltralyticsAddonModel] = {}
    for capability, setting_name, task in (
        ("threat", "threat", "threat"),
        ("plates", "plate", "plates"),
        ("pose", "pose", "pose"),
    ):
        if not getattr(settings, f"addon_{setting_name}_model_enabled"):
            continue
        models[capability] = UltralyticsAddonModel(
            model_path=getattr(settings, f"addon_{setting_name}_model_path"),
            expected_sha256=getattr(settings, f"addon_{setting_name}_model_sha256"),
            requested_device=settings.model_device,
            cuda_device_index=settings.model_cuda_device_index,
            task=task,
        )
    confirmation = PoseConfirmation(
        required_frames=settings.addon_pose_confirmation_frames,
        expiry_seconds=settings.addon_pose_confirmation_expiry_seconds,
        confidence_threshold=settings.addon_pose_confidence_threshold,
        minimum_iou=settings.addon_pose_minimum_iou,
    )
    ocr = TesseractPlateOCR() if settings.addon_plate_ocr_enabled else None
    return AddonRuntime(
        pipeline=AnalysisPipeline(
            threat=models.get("threat"),
            plates=models.get("plates"),
            pose=models.get("pose"),
            plate_ocr=ocr,
            pose_confirmation=confirmation,
        ),
        models=models,
    )
