from __future__ import annotations

from api.dependencies.core import (
    get_frame_processor,
    get_inference_gate,
    get_model_lifecycle,
    get_model_registry,
    get_settings_from_app,
)
from api.dependencies.streams import (
    StreamManagerDependency,
    StreamWorkerFactoryDependency,
    get_stream_manager,
    get_stream_worker_factory,
)

__all__ = [
    "StreamManagerDependency",
    "StreamWorkerFactoryDependency",
    "get_frame_processor",
    "get_inference_gate",
    "get_model_lifecycle",
    "get_model_registry",
    "get_settings_from_app",
    "get_stream_manager",
    "get_stream_worker_factory",
]
