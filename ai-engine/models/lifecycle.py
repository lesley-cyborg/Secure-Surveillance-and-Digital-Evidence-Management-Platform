from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

import structlog

from detection.detector import Detector
from detection.exceptions import (
    DetectionEngineError,
    DetectorNotFoundError,
    ModelLifecycleError,
)
from detection.model_registry import ModelRegistry

logger = structlog.get_logger(__name__)


class ManagedDetector(
    Detector,
    Protocol,
):
    def load(self) -> None:
        """Load runtime resources."""

    def warm_up(self) -> None:
        """Run warm-up inference."""

    def unload(self) -> None:
        """Release runtime resources."""


type DetectorFactory = Callable[[], ManagedDetector]


class ModelLifecycleState(StrEnum):
    DISABLED = "disabled"
    STOPPED = "stopped"
    LOADING = "loading"
    WARMING = "warming"
    READY = "ready"
    STOPPING = "stopping"
    FAILED = "failed"


class ModelLifecycleManager:
    def __init__(
        self,
        *,
        enabled: bool,
        registry: ModelRegistry,
        detector_factory: DetectorFactory,
        warmup_runs: int = 1,
    ) -> None:
        if warmup_runs < 0:
            raise ValueError("warmup_runs cannot be negative")

        self._enabled = enabled
        self._registry = registry
        self._detector_factory = detector_factory
        self._warmup_runs = warmup_runs

        self._detector: ManagedDetector | None = None
        self._state = (
            ModelLifecycleState.STOPPED if enabled else ModelLifecycleState.DISABLED
        )
        self._last_error: str | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> ModelLifecycleState:
        return self._state

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def detector(self) -> ManagedDetector | None:
        return self._detector

    async def startup(self) -> None:
        async with self._lock:
            if not self._enabled:
                self._state = ModelLifecycleState.DISABLED
                return

            if self._state is ModelLifecycleState.READY:
                return

            self._state = ModelLifecycleState.LOADING
            self._last_error = None

            detector = self._detector_factory()

            try:
                await asyncio.to_thread(detector.load)

                self._state = ModelLifecycleState.WARMING

                for _ in range(self._warmup_runs):
                    await asyncio.to_thread(detector.warm_up)

                self._registry.register(
                    detector,
                    make_default=True,
                    make_name_default=True,
                )
            except Exception as exception:
                await self._safe_unload(detector)

                self._state = ModelLifecycleState.FAILED
                self._last_error = str(exception)

                logger.exception(
                    "production_model_startup_failed",
                    error_type=(type(exception).__name__),
                )

                if isinstance(
                    exception,
                    DetectionEngineError,
                ):
                    raise

                raise ModelLifecycleError(
                    "Production model startup failed"
                ) from exception

            self._detector = detector
            self._state = ModelLifecycleState.READY

            logger.info(
                "production_model_ready",
                model_name=detector.identity.name,
                model_version=(detector.identity.version),
                device=(detector.identity.device.value),
                warmup_runs=self._warmup_runs,
            )

    async def shutdown(self) -> None:
        logger.info(
            "production_model_shutdown_started",
            lifecycle_state=self._state.value,
        )

        async with self._lock:
            detector = self._detector

            if detector is None:
                self._state = (
                    ModelLifecycleState.STOPPED
                    if self._enabled
                    else ModelLifecycleState.DISABLED
                )
                self._last_error = None

                logger.info(
                    "production_model_shutdown_skipped",
                    reason="detector_not_loaded",
                    lifecycle_state=(self._state.value),
                )
                return

            identity = detector.identity
            self._state = ModelLifecycleState.STOPPING
            self._last_error = None

            logger.info(
                "production_model_unregister_started",
                model_name=identity.name,
                model_version=identity.version,
            )

            try:
                self._registry.unregister(
                    name=identity.name,
                    version=identity.version,
                )
            except DetectorNotFoundError:
                logger.warning(
                    "production_model_already_unregistered",
                    model_name=identity.name,
                    model_version=identity.version,
                )

            self._detector = None

            logger.info(
                "production_model_unregistered",
                model_name=identity.name,
                model_version=identity.version,
            )

        logger.info(
            "production_model_unload_started",
            model_name=identity.name,
            model_version=identity.version,
        )

        try:
            await asyncio.to_thread(detector.unload)
        except Exception as exception:
            async with self._lock:
                self._state = ModelLifecycleState.FAILED
                self._last_error = str(exception)

            logger.exception(
                "production_model_shutdown_failed",
                model_name=identity.name,
                model_version=identity.version,
                error_type=(type(exception).__name__),
            )

            raise ModelLifecycleError("Production model shutdown failed") from exception

        logger.info(
            "production_model_unloaded",
            model_name=identity.name,
            model_version=identity.version,
        )

        async with self._lock:
            self._state = ModelLifecycleState.STOPPED
            self._last_error = None

        logger.info(
            "production_model_stopped",
            model_name=identity.name,
            model_version=identity.version,
        )

        logger.info(
            "production_model_shutdown_finished",
            model_name=identity.name,
            model_version=identity.version,
            lifecycle_state=self._state.value,
        )

    @staticmethod
    async def _safe_unload(
        detector: ManagedDetector,
    ) -> None:
        try:
            await asyncio.to_thread(detector.unload)
        except Exception:
            logger.exception("production_model_cleanup_failed")
