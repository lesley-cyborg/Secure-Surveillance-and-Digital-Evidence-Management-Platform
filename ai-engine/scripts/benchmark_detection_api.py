from __future__ import annotations

import argparse
import json
import math
import mimetypes
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any

import httpx


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Benchmark the production image detection endpoint.")
    )
    parser.add_argument(
        "--image",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--url",
        default=("http://127.0.0.1:8001/api/v1/detect/image"),
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.35,
    )

    return parser.parse_args()


def percentile(
    values: list[float],
    percentile_value: float,
) -> float:
    ordered = sorted(values)

    index = max(
        0,
        math.ceil(percentile_value * len(ordered)) - 1,
    )

    return ordered[index]


def submit_image(
    client: httpx.Client,
    *,
    url: str,
    image_path: Path,
    image_payload: bytes,
    media_type: str,
    confidence: float,
) -> tuple[float, float, int]:
    started_at = perf_counter()

    response = client.post(
        url,
        files={
            "file": (
                image_path.name,
                image_payload,
                media_type,
            )
        },
        data={"confidence_threshold": str(confidence)},
    )

    wall_duration_ms = (perf_counter() - started_at) * 1_000

    if response.is_error:
        print(response.text)
        response.raise_for_status()

    body: dict[str, Any] = response.json()

    return (
        float(body["inference_duration_ms"]),
        wall_duration_ms,
        len(body["detections"]),
    )


def main() -> None:
    arguments = parse_arguments()

    if arguments.runs <= 0:
        raise SystemExit("--runs must be greater than zero.")

    if arguments.warmup < 0:
        raise SystemExit("--warmup cannot be negative.")

    image_path: Path = arguments.image

    if not image_path.is_file():
        raise SystemExit(f"Image does not exist: {image_path}")

    media_type, _ = mimetypes.guess_type(image_path.name)

    if media_type not in {
        "image/jpeg",
        "image/png",
    }:
        raise SystemExit("The image must be JPEG or PNG.")

    image_payload = image_path.read_bytes()

    server_durations: list[float] = []
    wall_durations: list[float] = []
    detection_counts: list[int] = []

    with httpx.Client(timeout=120.0) as client:
        for _ in range(arguments.warmup):
            submit_image(
                client,
                url=arguments.url,
                image_path=image_path,
                image_payload=image_payload,
                media_type=media_type,
                confidence=arguments.confidence,
            )

        for run_number in range(
            1,
            arguments.runs + 1,
        ):
            (
                server_duration,
                wall_duration,
                detection_count,
            ) = submit_image(
                client,
                url=arguments.url,
                image_path=image_path,
                image_payload=image_payload,
                media_type=media_type,
                confidence=arguments.confidence,
            )

            server_durations.append(server_duration)
            wall_durations.append(wall_duration)
            detection_counts.append(detection_count)

            print(
                f"Run {run_number:02d}: "
                f"inference={server_duration:.2f} ms, "
                f"wall={wall_duration:.2f} ms, "
                f"detections={detection_count}"
            )

    report = {
        "image": str(image_path.resolve()),
        "runs": arguments.runs,
        "warmup_runs": arguments.warmup,
        "confidence_threshold": (arguments.confidence),
        "server_inference_ms": {
            "minimum": min(server_durations),
            "mean": mean(server_durations),
            "median": median(server_durations),
            "p95": percentile(
                server_durations,
                0.95,
            ),
            "maximum": max(server_durations),
        },
        "end_to_end_ms": {
            "minimum": min(wall_durations),
            "mean": mean(wall_durations),
            "median": median(wall_durations),
            "p95": percentile(
                wall_durations,
                0.95,
            ),
            "maximum": max(wall_durations),
        },
        "detection_counts": (detection_counts),
    }

    output_path = Path("benchmark-results.json")

    output_path.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        json.dumps(
            report,
            indent=2,
        )
    )
    print()
    print(f"Saved benchmark to {output_path}")


if __name__ == "__main__":
    main()
