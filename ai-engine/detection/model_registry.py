from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from detection.detector import Detector
from detection.exceptions import (
    DefaultDetectorNotConfiguredError,
    DetectorAlreadyRegisteredError,
    DetectorNotFoundError,
)
from detection.schemas import ModelStatus


@dataclass(frozen=True, order=True, slots=True)
class ModelKey:
    name: str
    version: str


class ModelRegistry:
    """
    Thread-safe registry for detector implementations.

    The first registered detector becomes the default unless another
    detector is explicitly marked as default.
    """

    def __init__(self) -> None:
        self._detectors: dict[
            ModelKey,
            Detector,
        ] = {}

        self._default_key: ModelKey | None = None

        self._name_defaults: dict[
            str,
            ModelKey,
        ] = {}

        self._lock = RLock()

    def register(
        self,
        detector: Detector,
        *,
        make_default: bool = False,
        make_name_default: bool = False,
    ) -> None:
        identity = detector.identity

        key = ModelKey(
            name=identity.name,
            version=identity.version,
        )

        with self._lock:
            if key in self._detectors:
                raise DetectorAlreadyRegisteredError(
                    f"Detector already registered: {key.name}:{key.version}"
                )

            self._detectors[key] = detector

            if key.name not in self._name_defaults or make_name_default:
                self._name_defaults[key.name] = key

            if self._default_key is None or make_default:
                self._default_key = key

    def resolve(
        self,
        *,
        name: str | None = None,
        version: str | None = None,
    ) -> Detector:
        with self._lock:
            key = self._resolve_key(
                name=name,
                version=version,
            )

            try:
                return self._detectors[key]
            except KeyError as exc:
                raise DetectorNotFoundError(
                    f"Detector not found: {key.name}:{key.version}"
                ) from exc

    def unregister(
        self,
        *,
        name: str,
        version: str,
    ) -> Detector:
        key = ModelKey(
            name=name,
            version=version,
        )

        with self._lock:
            try:
                detector = self._detectors.pop(key)
            except KeyError as exc:
                raise DetectorNotFoundError(
                    f"Detector not found: {name}:{version}"
                ) from exc

            self._repair_defaults_after_removal(key)

            return detector

    def set_default(
        self,
        *,
        name: str,
        version: str,
    ) -> None:
        key = ModelKey(
            name=name,
            version=version,
        )

        with self._lock:
            if key not in self._detectors:
                raise DetectorNotFoundError(f"Detector not found: {name}:{version}")

            self._default_key = key
            self._name_defaults[name] = key

    def list_models(
        self,
    ) -> tuple[ModelStatus, ...]:
        with self._lock:
            return tuple(
                ModelStatus(
                    model=detector.identity,
                    is_ready=detector.is_ready,
                    is_default=(key == self._default_key),
                )
                for key, detector in sorted(
                    self._detectors.items(),
                    key=lambda item: item[0],
                )
            )

    def _resolve_key(
        self,
        *,
        name: str | None,
        version: str | None,
    ) -> ModelKey:
        if name is None and version is None:
            if self._default_key is None:
                raise (
                    DefaultDetectorNotConfiguredError(
                        "No default detector is configured"
                    )
                )

            return self._default_key

        if name is None:
            raise DetectorNotFoundError(
                "A model name is required when a model version is supplied"
            )

        if version is not None:
            return ModelKey(
                name=name,
                version=version,
            )

        try:
            return self._name_defaults[name]
        except KeyError as exc:
            raise DetectorNotFoundError(f"No detector is registered as {name}") from exc

    def _repair_defaults_after_removal(
        self,
        removed_key: ModelKey,
    ) -> None:
        remaining_keys = sorted(self._detectors)

        if self._default_key == removed_key:
            self._default_key = remaining_keys[0] if remaining_keys else None

        if self._name_defaults.get(removed_key.name) == removed_key:
            replacements = [
                key for key in remaining_keys if key.name == removed_key.name
            ]

            if replacements:
                self._name_defaults[removed_key.name] = replacements[0]
            else:
                self._name_defaults.pop(
                    removed_key.name,
                    None,
                )
