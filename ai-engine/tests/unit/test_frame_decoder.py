from __future__ import annotations

from uuid import uuid4

import cv2
import numpy as np
import pytest

from detection.exceptions import (
    EmptyFrameError,
    FrameTooLargeError,
    InvalidFrameError,
    UnsupportedMediaTypeError,
)
from detection.frame_decoder import (
    FrameDecoder,
    VideoFrame,
)
from detection.schemas import MediaType


def _decoder(
    *,
    maximum_bytes: int = 5_000_000,
    maximum_width: int = 4096,
    maximum_height: int = 4096,
    maximum_pixels: int = 16_000_000,
) -> FrameDecoder:
    return FrameDecoder(
        maximum_bytes=maximum_bytes,
        maximum_width=maximum_width,
        maximum_height=maximum_height,
        maximum_pixels=maximum_pixels,
    )


def _encoded_image(
    extension: str,
    *,
    width: int = 320,
    height: int = 240,
    channels: int = 3,
) -> bytes:
    if channels == 1:
        image = np.zeros(
            (height, width),
            dtype=np.uint8,
        )
    else:
        image = np.zeros(
            (height, width, channels),
            dtype=np.uint8,
        )

    success, encoded = cv2.imencode(
        extension,
        image,
    )

    assert success is True

    return encoded.tobytes()


@pytest.mark.parametrize(
    ("extension", "media_type"),
    [
        (".jpg", MediaType.JPEG),
        (".png", MediaType.PNG),
    ],
)
def test_decoder_accepts_jpeg_and_png(
    extension: str,
    media_type: MediaType,
) -> None:
    decoded = _decoder().decode_image(
        _encoded_image(extension),
        media_type,
    )

    assert decoded.metadata.width == 320
    assert decoded.metadata.height == 240
    assert decoded.metadata.channels == 3
    assert decoded.metadata.media_type is media_type
    assert decoded.image.shape == (
        240,
        320,
        3,
    )


def test_decoder_converts_grayscale_to_bgr() -> None:
    decoded = _decoder().decode_image(
        _encoded_image(
            ".png",
            channels=1,
        ),
        MediaType.PNG,
    )

    assert decoded.image.shape == (
        240,
        320,
        3,
    )
    assert decoded.metadata.channels == 3


def test_decoder_rejects_empty_payload() -> None:
    with pytest.raises(EmptyFrameError):
        _decoder().decode_image(
            b"",
            MediaType.JPEG,
        )


def test_decoder_rejects_corrupt_payload() -> None:
    corrupt_payload = FrameDecoder.JPEG_SIGNATURE + b"not-a-valid-image"

    with pytest.raises(InvalidFrameError):
        _decoder().decode_image(
            corrupt_payload,
            MediaType.JPEG,
        )


def test_decoder_rejects_mismatched_media_type() -> None:
    png_payload = _encoded_image(".png")

    with pytest.raises(InvalidFrameError):
        _decoder().decode_image(
            png_payload,
            MediaType.JPEG,
        )


def test_decoder_rejects_unsupported_media_type() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        _decoder().decode_image(
            b"GIF89a",
            "image/gif",
        )


def test_decoder_rejects_large_byte_payload() -> None:
    payload = _encoded_image(".png")

    with pytest.raises(FrameTooLargeError):
        _decoder(maximum_bytes=10).decode_image(
            payload,
            MediaType.PNG,
        )


def test_decoder_rejects_large_dimensions() -> None:
    payload = _encoded_image(
        ".png",
        width=200,
        height=100,
    )

    with pytest.raises(FrameTooLargeError):
        _decoder(maximum_width=100).decode_image(
            payload,
            MediaType.PNG,
        )


def test_video_frame_rejects_negative_index() -> None:
    decoded = _decoder().decode_image(
        _encoded_image(".jpg"),
        MediaType.JPEG,
    )

    with pytest.raises(ValueError):
        VideoFrame(
            source_id=uuid4(),
            frame_index=-1,
            timestamp_ms=0,
            decoded_frame=decoded,
        )


def test_decoder_rejects_unsupported_pixel_depth() -> None:
    image = np.zeros(
        (100, 100),
        dtype=np.uint16,
    )

    success, encoded = cv2.imencode(
        ".png",
        image,
    )

    assert success is True

    with pytest.raises(
        InvalidFrameError,
        match="Only 8-bit",
    ):
        _decoder().decode_image(
            encoded.tobytes(),
            MediaType.PNG,
        )
