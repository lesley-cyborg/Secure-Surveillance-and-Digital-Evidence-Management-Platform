from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

SUPPORTED_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Submit a real image to the production detection API.")
    )
    parser.add_argument(
        "--image",
        type=Path,
        required=True,
        help="Path to a JPEG or PNG image.",
    )
    parser.add_argument(
        "--url",
        default=("http://127.0.0.1:8001/api/v1/detect/image"),
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.35,
    )

    return parser.parse_args()


def validate_detection_result(
    body: dict[str, Any],
    *,
    correlation_id: str,
) -> None:
    assert body["correlation_id"] == correlation_id
    assert body["model"]["name"] == ("surveillance-yolo")
    assert body["model"]["version"] == ("yolo26n-coco")
    assert body["model"]["device"] in {
        "cpu",
        "cuda",
    }

    assert body["frame"]["width"] > 0
    assert body["frame"]["height"] > 0
    assert body["inference_duration_ms"] >= 0

    for detection in body["detections"]:
        confidence = detection["confidence"]

        assert 0 <= confidence <= 1

        bounding_box = detection["bounding_box"]

        assert 0 <= bounding_box["x_min"] < bounding_box["x_max"] <= 1
        assert 0 <= bounding_box["y_min"] < bounding_box["y_max"] <= 1


def main() -> None:
    arguments = parse_arguments()
    image_path: Path = arguments.image

    if not image_path.is_file():
        raise SystemExit(f"Image does not exist: {image_path}")

    media_type, _ = mimetypes.guess_type(image_path.name)

    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise SystemExit("The image must be JPEG or PNG.")

    correlation_id = str(uuid4())

    with image_path.open("rb") as image_file:
        response = httpx.post(
            arguments.url,
            headers={"X-Correlation-ID": (correlation_id)},
            files={
                "file": (
                    image_path.name,
                    image_file,
                    media_type,
                )
            },
            data={"confidence_threshold": str(arguments.confidence)},
            timeout=120.0,
        )

    if response.is_error:
        print(response.text)
        response.raise_for_status()

    body: dict[str, Any] = response.json()

    validate_detection_result(
        body,
        correlation_id=correlation_id,
    )

    print(
        json.dumps(
            body,
            indent=2,
        )
    )

    print()
    print(
        "Detections:",
        len(body["detections"]),
    )
    print(
        "Inference duration:",
        f"{body['inference_duration_ms']:.2f} ms",
    )
    print(
        "Correlation ID:",
        body["correlation_id"],
    )


if __name__ == "__main__":
    main()
