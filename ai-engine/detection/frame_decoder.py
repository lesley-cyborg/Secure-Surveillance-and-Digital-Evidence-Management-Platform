from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

import cv2
import numpy as np

from detection.detector import FrameArray
from detection.exceptions import (
    EmptyFrameError,
    FrameTooLargeError,
    InvalidFrameError,
    UnsupportedMediaTypeError,
)
from detection.schemas import (
    FrameMetadata,
    MediaType,
)


@dataclass(frozen=True, slots=True)
class DecodedFrame:
    image: FrameArray
    metadata: FrameMetadata


@dataclass(frozen=True, slots=True)
class VideoFrame:
    """
    Model-independent representation of a frame extracted from video.

    Actual video capture and streaming will be implemented in a later
    phase without changing the detector interface.
    """

    source_id: UUID | str
    frame_index: int
    timestamp_ms: float
    decoded_frame: DecodedFrame

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("Video frame index cannot be negative")

        if self.timestamp_ms < 0:
            raise ValueError("Video frame timestamp cannot be negative")


class FrameDecoder:
    JPEG_SIGNATURE = b"\xff\xd8\xff"
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    def __init__(
        self,
        *,
        maximum_bytes: int,
        maximum_width: int,
        maximum_height: int,
        maximum_pixels: int,
    ) -> None:
        if maximum_bytes <= 0:
            raise ValueError("Maximum byte size must be positive")

        if maximum_width <= 0:
            raise ValueError("Maximum width must be positive")

        if maximum_height <= 0:
            raise ValueError("Maximum height must be positive")

        if maximum_pixels <= 0:
            raise ValueError("Maximum pixel count must be positive")

        self.maximum_bytes = maximum_bytes
        self.maximum_width = maximum_width
        self.maximum_height = maximum_height
        self.maximum_pixels = maximum_pixels

    def decode_image(
        self,
        payload: bytes,
        media_type: MediaType | str,
    ) -> DecodedFrame:
        resolved_media_type = self._resolve_media_type(media_type)

        self._validate_payload_size(payload)
        self._validate_signature(
            payload,
            resolved_media_type,
        )

        encoded = np.frombuffer(
            payload,
            dtype=np.uint8,
        )

        if encoded.size == 0:
            raise EmptyFrameError("The submitted image is empty")

        decoded = cv2.imdecode(
            encoded,
            cv2.IMREAD_UNCHANGED,
        )

        if decoded is None:
            raise InvalidFrameError("The submitted image could not be decoded")

        if decoded.size == 0:
            raise EmptyFrameError("The decoded image contains no pixels")

        if decoded.dtype != np.uint8:
            raise InvalidFrameError("Only 8-bit JPEG and PNG images are supported")

        typed_decoded = cast(
            FrameArray,
            decoded,
        )

        image = self._convert_to_bgr(typed_decoded)
        height, width = image.shape[:2]

        self._validate_dimensions(
            width=width,
            height=height,
        )

        contiguous_image = np.ascontiguousarray(
            image,
            dtype=np.uint8,
        )

        metadata = FrameMetadata(
            width=width,
            height=height,
            channels=3,
            media_type=resolved_media_type,
            byte_size=len(payload),
        )

        return DecodedFrame(
            image=contiguous_image,
            metadata=metadata,
        )

    def _validate_payload_size(
        self,
        payload: bytes,
    ) -> None:
        if not payload:
            raise EmptyFrameError("The submitted image is empty")

        if len(payload) > self.maximum_bytes:
            raise FrameTooLargeError(
                "The submitted image exceeds the maximum byte size"
            )

    def _validate_dimensions(
        self,
        *,
        width: int,
        height: int,
    ) -> None:
        if width <= 0 or height <= 0:
            raise EmptyFrameError("The decoded image has invalid dimensions")

        if width > self.maximum_width or height > self.maximum_height:
            raise FrameTooLargeError(
                "The submitted image dimensions exceed the configured limit"
            )

        if width * height > self.maximum_pixels:
            raise FrameTooLargeError("The submitted image contains too many pixels")

    @classmethod
    def _resolve_media_type(
        cls,
        media_type: MediaType | str,
    ) -> MediaType:
        if isinstance(media_type, MediaType):
            return media_type

        try:
            return MediaType(media_type.casefold())
        except ValueError as exc:
            raise UnsupportedMediaTypeError(
                f"Unsupported media type: {media_type}"
            ) from exc

    @classmethod
    def _validate_signature(
        cls,
        payload: bytes,
        media_type: MediaType,
    ) -> None:
        if media_type is MediaType.JPEG:
            valid = payload.startswith(cls.JPEG_SIGNATURE)
        else:
            valid = payload.startswith(cls.PNG_SIGNATURE)

        if not valid:
            raise InvalidFrameError(
                "The image content does not match the declared media type"
            )

    @staticmethod
    def _convert_to_bgr(
        image: FrameArray,
    ) -> FrameArray:
        if image.ndim == 2:
            converted = cv2.cvtColor(
                image,
                cv2.COLOR_GRAY2BGR,
            )

            return np.asarray(
                converted,
                dtype=np.uint8,
            )

        if image.ndim != 3:
            raise InvalidFrameError("The decoded image has an unsupported shape")

        channel_count = image.shape[2]

        if channel_count == 3:
            return np.asarray(
                image,
                dtype=np.uint8,
            )

        if channel_count == 4:
            converted = cv2.cvtColor(
                image,
                cv2.COLOR_BGRA2BGR,
            )

            return np.asarray(
                converted,
                dtype=np.uint8,
            )

        raise InvalidFrameError(
            f"The decoded image has an unsupported channel count: {channel_count}"
        )
