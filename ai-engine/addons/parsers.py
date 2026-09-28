from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, cast

from addons.schemas import BoundingBox, PlateCandidate, PoseObservation, ThreatSignal

_WEAPON_ALIASES: dict[str, str] = {
    "knife": "knife",
    "sword": "sword",
    "rifle": "rifle",
    "pistol": "pistol",
    "handgun": "pistol",
    "gun": "pistol",
    "firearm": "firearm",
    "weapon": "weapon",   
}

_SKIP_LABELS: frozenset[str] = frozenset({"0", "person"})


def normalize_threat_label(raw: str) -> str | None:
    key = raw.strip().casefold().replace(" ", "_")
    if key in _SKIP_LABELS or key == "":
        return None
    return _WEAPON_ALIASES.get(key)


class _PredictionBox(Protocol):
    cls: Any
    conf: Any
    xyxy: Any


class _PredictionResult(Protocol):
    boxes: Iterable[_PredictionBox]
    names: Mapping[int, str] | list[str]
    orig_shape: tuple[int, int] | list[int]


def _first_result(results: object) -> object | None:
    if isinstance(results, (tuple, list)):
        return results[0] if results else None
    return results


def _xyxy_box(coordinates: Iterable[float], width: int, height: int) -> BoundingBox:
    x_min, y_min, x_max, y_max = (float(value) for value in coordinates)
    left = max(0.0, min(1.0, x_min / width))
    top = max(0.0, min(1.0, y_min / height))
    right = max(0.0, min(1.0, x_max / width))
    bottom = max(0.0, min(1.0, y_max / height))
    if right <= left or bottom <= top:
        raise ValueError("model returned an invalid bounding box")
    return BoundingBox(x_min=left, y_min=top, x_max=right, y_max=bottom)


def _scalar(value: Any) -> float:
    if hasattr(value, "item"):
        return float(value.item())
    return float(value)


def _coordinates(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("model returned an invalid box")
    return [float(part) for part in value]


def _prediction_boxes(
    results: object,
) -> tuple[_PredictionResult | None, tuple[_PredictionBox, ...], int, int]:
    result = _first_result(results)
    if result is None or not hasattr(result, "boxes"):
        return None, (), 0, 0
    result = cast(_PredictionResult, result)
    shape = getattr(result, "orig_shape", None)
    if not isinstance(shape, (tuple, list)) or len(shape) != 2:
        raise ValueError("model result is missing its original image dimensions")
    height, width = int(shape[0]), int(shape[1])
    if width <= 0 or height <= 0:
        raise ValueError("model returned invalid image dimensions")
    return result, tuple(result.boxes), width, height


def parse_threat_predictions(results: object) -> tuple[ThreatSignal, ...]:
    result, boxes, width, height = _prediction_boxes(results)
    if result is None:
        return ()

    signals: list[ThreatSignal] = []
    for box in boxes:
        class_id = int(_scalar(box.cls[0]))
        label = str(result.names[class_id])
        normalized = normalize_threat_label(label)
        if normalized is None:
            continue

        signals.append(
            ThreatSignal(
                signal=label,
                confidence=max(0.0, min(1.0, _scalar(box.conf[0]))),
                source="weapon-detector",
                bounding_box=_xyxy_box(_coordinates(box.xyxy[0]), width, height),
            )
        )
    return tuple(signals)


def parse_plate_predictions(results: object) -> tuple[PlateCandidate, ...]:
    _, boxes, width, height = _prediction_boxes(results)
    return tuple(
        PlateCandidate(
            confidence=max(0.0, min(1.0, _scalar(box.conf[0]))),
            bounding_box=_xyxy_box(_coordinates(box.xyxy[0]), width, height),
        )
        for box in boxes
    )


def parse_pose_predictions(results: object) -> tuple[PoseObservation, ...]:
    _, boxes, width, height = _prediction_boxes(results)
    return tuple(
        PoseObservation(
            posture="person",
            confidence=max(0.0, min(1.0, _scalar(box.conf[0]))),
            bounding_box=_xyxy_box(_coordinates(box.xyxy[0]), width, height),
        )
        for box in boxes
    )
