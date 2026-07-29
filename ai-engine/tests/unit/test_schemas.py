from __future__ import annotations

import pytest
from pydantic import ValidationError

from detection.exceptions import (
    InvalidBoundingBoxError,
)
from detection.schemas import (
    NormalisedBoundingBox,
    PixelBoundingBox,
    RawDetection,
)


def test_pixel_bounding_box_normalises_coordinates() -> None:
    bounding_box = PixelBoundingBox(
        x_min=100,
        y_min=50,
        x_max=300,
        y_max=250,
    )

    normalised = bounding_box.normalise(
        frame_width=400,
        frame_height=500,
    )

    assert normalised == NormalisedBoundingBox(
        x_min=0.25,
        y_min=0.1,
        x_max=0.75,
        y_max=0.5,
    )


def test_bounding_box_rejects_reversed_coordinates() -> None:
    with pytest.raises(ValidationError):
        PixelBoundingBox(
            x_min=100,
            y_min=50,
            x_max=10,
            y_max=250,
        )


def test_bounding_box_rejects_frame_overflow() -> None:
    bounding_box = PixelBoundingBox(
        x_min=0,
        y_min=0,
        x_max=500,
        y_max=200,
    )

    with pytest.raises(InvalidBoundingBoxError):
        bounding_box.normalise(
            frame_width=400,
            frame_height=300,
        )


def test_detection_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        RawDetection(
            class_id=0,
            label="person",
            confidence=1.5,
            bounding_box=PixelBoundingBox(
                x_min=10,
                y_min=10,
                x_max=100,
                y_max=100,
            ),
        )


def test_detection_trims_label() -> None:
    detection = RawDetection(
        class_id=0,
        label="  person  ",
        confidence=0.9,
        bounding_box=PixelBoundingBox(
            x_min=10,
            y_min=10,
            x_max=100,
            y_max=100,
        ),
    )

    assert detection.label == "person"
