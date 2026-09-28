from __future__ import annotations

from typing import cast

from fastapi import Request

from addons.pipeline import AnalysisPipeline
from addons.runtime import AddonRuntime
from config.settings import Settings
from detection.frame_processor import (
    FrameProcessor,
)
from detection.inference_gate import (
    InferenceGate,
)
from detection.model_registry import (
    ModelRegistry,
)
from models.lifecycle import (
    ModelLifecycleManager,
)
from vision.analysis import VisionAnalyzer


def get_settings_from_app(
    request: Request,
) -> Settings:
    return cast(
        Settings,
        request.app.state.settings,
    )


def get_model_registry(
    request: Request,
) -> ModelRegistry:
    return cast(
        ModelRegistry,
        request.app.state.model_registry,
    )


def get_frame_processor(
    request: Request,
) -> FrameProcessor:
    return cast(
        FrameProcessor,
        request.app.state.frame_processor,
    )


def get_inference_gate(
    request: Request,
) -> InferenceGate:
    return cast(
        InferenceGate,
        request.app.state.inference_gate,
    )


def get_model_lifecycle(
    request: Request,
) -> ModelLifecycleManager:
    return cast(
        ModelLifecycleManager,
        request.app.state.model_lifecycle,
    )


def get_vision_analyzer(
    request: Request,
) -> VisionAnalyzer:
    return cast(VisionAnalyzer, request.app.state.vision_analyzer)


def get_addon_pipeline(
    request: Request,
) -> AnalysisPipeline | None:
    runtime = cast(
        AddonRuntime | None,
        getattr(request.app.state, "addon_runtime", None),
    )
    if runtime is None: 
        return None
    return runtime.pipeline
