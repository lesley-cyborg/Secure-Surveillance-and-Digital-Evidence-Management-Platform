from __future__ import annotations

from config.settings import Settings
from models.ultralytics_detector import (
    UltralyticsDetector,
)


def create_production_detector(
    settings: Settings,
) -> UltralyticsDetector:
    return UltralyticsDetector(
        model_path=settings.model_path,
        model_name=settings.model_name,
        model_version=(settings.model_version),
        requested_device=(settings.model_device),
        cuda_device_index=(settings.model_cuda_device_index),
        image_size=(settings.model_image_size),
        backend_confidence_floor=(settings.model_backend_confidence_floor),
        iou_threshold=(settings.model_iou_threshold),
        allowed_labels=(settings.model_allowed_labels),
        expected_sha256=(settings.model_sha256),
    )
