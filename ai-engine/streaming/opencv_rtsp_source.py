from __future__ import annotations

import math
import os
from collections.abc import (
    Callable,
    Iterator,
    Sequence,
)
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import RLock
from types import TracebackType
from typing import (
    Protocol,
    Self,
    cast,
)

import cv2
import numpy as np
import structlog

from streaming.domain import (
    CameraStreamConfig,
    FrameArray,
    StreamFrame,
    StreamTransport,
)
from streaming.exceptions import (
    StreamDisabledError,
    StreamNotOpenError,
    StreamOpenError,
    StreamReadError,
)

logger = structlog.get_logger(__name__)


class VideoCaptureLike(Protocol):
    """Small testable subset of cv2.VideoCapture."""

    def open(
        self,
        filename: str,
        api_preference: int,
        params: Sequence[int],
    ) -> bool:
        """Open a video source."""

    def isOpened(self) -> bool:
        """Return whether the source is open."""

    def read(
        self,
    ) -> tuple[
        bool,
        FrameArray | None,
    ]:
        """Read the next decoded frame."""

    def release(self) -> None:
        """Release the video source."""

    def get(
        self,
        property_id: int,
    ) -> float:
        """Read a capture property."""

    def getBackendName(self) -> str:
        """Return the selected backend name."""


type CaptureFactory = Callable[
    [],
    VideoCaptureLike,
]


def _create_opencv_capture() -> VideoCaptureLike:
    return cast(
        VideoCaptureLike,
        cv2.VideoCapture(),
    )


class OpenCvRtspSource:
    """OpenCV-backed RTSP camera source.

    Each instance manages one VideoCapture object. Operations are
    serialised because OpenCV capture objects are not shared between
    concurrent reader threads.
    """

    _ffmpeg_environment_lock = RLock()
    _ffmpeg_options_variable = "OPENCV_FFMPEG_CAPTURE_OPTIONS"

    def __init__(
        self,
        *,
        config: CameraStreamConfig,
        capture_factory: CaptureFactory | None = None,
        backend_api: int | None = None,
    ) -> None:
        self._config = config
        self._capture_factory = capture_factory or _create_opencv_capture
        self._backend_api = int(cv2.CAP_FFMPEG) if backend_api is None else backend_api

        self._capture: VideoCaptureLike | None = None
        self._backend_name: str | None = None
        self._sequence_number = 0
        self._lock = RLock()

    @property
    def config(self) -> CameraStreamConfig:
        return self._config

    @property
    def is_open(self) -> bool:
        with self._lock:
            capture = self._capture

            if capture is None:
                return False

            try:
                return bool(capture.isOpened())
            except Exception:
                return False

    @property
    def backend_name(self) -> str | None:
        with self._lock:
            return self._backend_name

    def open(self) -> None:
        with self._lock:
            if not self._config.enabled:
                raise StreamDisabledError(
                    f"Camera {self._config.camera_id!r} is disabled"
                )

            if self._capture_is_open():
                return

            self._release_current_capture()

            capture = self._capture_factory()
            parameters = self._build_open_parameters()

            try:
                with self._temporary_ffmpeg_options():
                    opened = capture.open(
                        self._config.source_uri,
                        self._backend_api,
                        parameters,
                    )

                if not opened or not capture.isOpened():
                    raise StreamOpenError(
                        "Could not open camera stream "
                        f"{self._config.redacted_source_uri}"
                    )
            except StreamOpenError:
                self._safe_release(capture)
                raise
            except Exception as exception:
                self._safe_release(capture)

                raise StreamOpenError(
                    f"Could not open camera stream {self._config.redacted_source_uri}"
                ) from exception

            self._capture = capture
            self._sequence_number = 0
            self._backend_name = self._read_backend_name(capture)

            logger.info(
                "rtsp_source_opened",
                camera_id=self._config.camera_id,
                source_uri=(self._config.redacted_source_uri),
                transport=(self._config.transport.value),
                backend=self._backend_name,
                connect_timeout_seconds=(self._config.connect_timeout_seconds),
                read_timeout_seconds=(self._config.read_timeout_seconds),
            )

    def read(self) -> StreamFrame:
        with self._lock:
            capture = self._capture

            if capture is None or not self._capture_is_open():
                raise StreamNotOpenError(
                    f"Camera stream {self._config.camera_id!r} is not open"
                )

            try:
                successful, image = capture.read()
            except Exception as exception:
                raise StreamReadError(
                    f"Failed to read from camera {self._config.camera_id!r}"
                ) from exception

            if not successful or image is None:
                raise StreamReadError(
                    f"Camera {self._config.camera_id!r} did not return a frame"
                )

            if not isinstance(
                image,
                np.ndarray,
            ):
                raise StreamReadError("Camera returned an invalid frame object")

            if image.size == 0:
                raise StreamReadError("Camera returned an empty frame")

            if image.dtype != np.uint8:
                raise StreamReadError("Camera frame must use uint8 pixels")

            if image.ndim != 3 or image.shape[2] != 3:
                raise StreamReadError("Camera frame must contain three BGR channels")

            received_at = datetime.now(UTC)

            frame = StreamFrame(
                camera_id=self._config.camera_id,
                sequence_number=(self._sequence_number),
                captured_at=received_at,
                received_at=received_at,
                image=image,
                source_timestamp_ms=(self._read_source_timestamp(capture)),
            )

            self._sequence_number += 1

            return frame

    def close(self) -> None:
        with self._lock:
            capture = self._capture

            self._capture = None
            self._backend_name = None
            self._sequence_number = 0

            if capture is None:
                return

            self._safe_release(capture)

            logger.info(
                "rtsp_source_closed",
                camera_id=self._config.camera_id,
                source_uri=(self._config.redacted_source_uri),
            )

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exception_type: (type[BaseException] | None),
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del (
            exception_type,
            exception,
            traceback,
        )

        self.close()

    def _capture_is_open(self) -> bool:
        capture = self._capture

        if capture is None:
            return False

        try:
            return bool(capture.isOpened())
        except Exception:
            return False

    def _release_current_capture(
        self,
    ) -> None:
        capture = self._capture

        self._capture = None
        self._backend_name = None

        if capture is not None:
            self._safe_release(capture)

    def _build_open_parameters(
        self,
    ) -> list[int]:
        return [
            int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC),
            self._seconds_to_milliseconds(self._config.connect_timeout_seconds),
            int(cv2.CAP_PROP_READ_TIMEOUT_MSEC),
            self._seconds_to_milliseconds(self._config.read_timeout_seconds),
        ]

    @contextmanager
    def _temporary_ffmpeg_options(
        self,
    ) -> Iterator[None]:
        """Apply per-open RTSP transport configuration.

        OpenCV exposes FFmpeg options through a process environment
        variable. A class-level lock prevents two adapter instances
        from modifying that variable during concurrent open calls.
        """

        with self._ffmpeg_environment_lock:
            previous_value = os.environ.get(self._ffmpeg_options_variable)

            try:
                transport = self._config.transport

                if transport is not StreamTransport.AUTO:
                    updated_value = self._merge_ffmpeg_option(
                        previous_value,
                        key="rtsp_transport",
                        value=transport.value,
                    )

                    os.environ[self._ffmpeg_options_variable] = updated_value

                yield
            finally:
                if previous_value is None:
                    os.environ.pop(
                        self._ffmpeg_options_variable,
                        None,
                    )
                else:
                    os.environ[self._ffmpeg_options_variable] = previous_value

    @staticmethod
    def _merge_ffmpeg_option(
        existing_options: str | None,
        *,
        key: str,
        value: str,
    ) -> str:
        option_prefix = f"{key};"

        existing_parts = existing_options.split("|") if existing_options else []

        retained_parts = [
            part
            for part in existing_parts
            if (part and not part.startswith(option_prefix))
        ]

        retained_parts.append(f"{key};{value}")

        return "|".join(retained_parts)

    @staticmethod
    def _read_backend_name(
        capture: VideoCaptureLike,
    ) -> str | None:
        try:
            backend_name = capture.getBackendName().strip()
        except Exception:
            return None

        return backend_name or None

    @staticmethod
    def _read_source_timestamp(
        capture: VideoCaptureLike,
    ) -> float | None:
        try:
            timestamp_ms = float(capture.get(int(cv2.CAP_PROP_POS_MSEC)))
        except Exception:
            return None

        if not math.isfinite(timestamp_ms) or timestamp_ms <= 0:
            return None

        return timestamp_ms

    @staticmethod
    def _seconds_to_milliseconds(
        seconds: float,
    ) -> int:
        return max(
            1,
            round(seconds * 1000),
        )

    @staticmethod
    def _safe_release(
        capture: VideoCaptureLike,
    ) -> None:
        try:
            capture.release()
        except Exception:
            logger.exception("rtsp_capture_release_failed")
