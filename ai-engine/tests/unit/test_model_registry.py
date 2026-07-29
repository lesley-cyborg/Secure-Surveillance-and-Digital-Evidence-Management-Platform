from __future__ import annotations

import pytest

from detection.detector import FrameArray
from detection.exceptions import (
    DefaultDetectorNotConfiguredError,
    DetectorAlreadyRegisteredError,
    DetectorNotFoundError,
)
from detection.model_registry import (
    ModelRegistry,
)
from detection.schemas import (
    DeviceType,
    ModelIdentity,
    RawDetection,
)


class FakeDetector:
    def __init__(
        self,
        *,
        name: str,
        version: str,
        ready: bool = True,
    ) -> None:
        self._identity = ModelIdentity(
            name=name,
            version=version,
            device=DeviceType.CPU,
            labels=("person",),
        )
        self._ready = ready

    @property
    def identity(self) -> ModelIdentity:
        return self._identity

    @property
    def is_ready(self) -> bool:
        return self._ready

    def detect(
        self,
        frame: FrameArray,
    ) -> tuple[RawDetection, ...]:
        del frame
        return ()


def test_registry_registers_multiple_versions() -> None:
    registry = ModelRegistry()

    version_one = FakeDetector(
        name="security-detector",
        version="1.0.0",
    )
    version_two = FakeDetector(
        name="security-detector",
        version="2.0.0",
    )

    registry.register(version_one)
    registry.register(version_two)

    assert (
        registry.resolve(
            name="security-detector",
            version="1.0.0",
        )
        is version_one
    )
    assert (
        registry.resolve(
            name="security-detector",
            version="2.0.0",
        )
        is version_two
    )


def test_registry_rejects_duplicate_version() -> None:
    registry = ModelRegistry()

    detector = FakeDetector(
        name="security-detector",
        version="1.0.0",
    )

    registry.register(detector)

    with pytest.raises(DetectorAlreadyRegisteredError):
        registry.register(detector)


def test_first_registered_detector_is_default() -> None:
    registry = ModelRegistry()

    detector = FakeDetector(
        name="security-detector",
        version="1.0.0",
    )

    registry.register(detector)

    assert registry.resolve() is detector


def test_explicit_default_replaces_default() -> None:
    registry = ModelRegistry()

    version_one = FakeDetector(
        name="security-detector",
        version="1.0.0",
    )
    version_two = FakeDetector(
        name="security-detector",
        version="2.0.0",
    )

    registry.register(version_one)
    registry.register(
        version_two,
        make_default=True,
        make_name_default=True,
    )

    assert registry.resolve() is version_two
    assert registry.resolve(name="security-detector") is version_two


def test_registry_unregisters_detector() -> None:
    registry = ModelRegistry()

    detector = FakeDetector(
        name="security-detector",
        version="1.0.0",
    )

    registry.register(detector)

    removed = registry.unregister(
        name="security-detector",
        version="1.0.0",
    )

    assert removed is detector

    with pytest.raises(DefaultDetectorNotConfiguredError):
        registry.resolve()


def test_registry_reports_model_health() -> None:
    registry = ModelRegistry()

    registry.register(
        FakeDetector(
            name="security-detector",
            version="1.0.0",
            ready=False,
        )
    )

    statuses = registry.list_models()

    assert len(statuses) == 1
    assert statuses[0].is_ready is False
    assert statuses[0].is_default is True


def test_registry_raises_for_missing_model() -> None:
    registry = ModelRegistry()

    with pytest.raises(DetectorNotFoundError):
        registry.resolve(
            name="missing",
            version="1.0.0",
        )
