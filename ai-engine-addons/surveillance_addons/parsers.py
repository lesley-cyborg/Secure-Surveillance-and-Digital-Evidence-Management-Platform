from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    BoundingBox,
    PlateObservation,
    PoseKeypoint,
    PoseObservation,
    ThreatSignal,
)


def _box(xyxy: Iterable[float], width: int, height: int) -> BoundingBox:
    x_min, y_min, x_max, y_max = (float(value) for value in xyxy)
    return BoundingBox(
        x_min=max(0.0, min(1.0, x_min / width)),
        y_min=max(0.0, min(1.0, y_min / height)),
        x_max=max(0.0, min(1.0, x_max / width)),
        y_max=max(0.0, min(1.0, y_max / height)),
    )


def _first_result(results: object) -> object:
    if isinstance(results, (tuple, list)):
        if not results:
            return None
        return results[0]
    return results


def prse_threat_predictions(results: object) -> tuple[ThreatSignal, ...]:
    result = _first_result(results)
    if result is None or not hasattr(result, "boxes"):
        return ()
    
    height, width = result.orig_shape
    names = result.names
    output: list[ThreatSignal] = []
    for box in result.boxes:
        class_id = int(box.cls[0])
        label = str(names[class_id])
        confidence = float(box.conf[0])
        output.append(
            ThreatSignal(
                signal=label,
                confidence=confidence,
                source="weapon-detector",
                bounding_box=_box(box.xyxy[0].tolist(),width, height),
            )
        )
    return tuple(output)


def parse_plate_predictions(results: object) -> tuple[PlateObservation, ...]:
    result = _first_result(results)
    if result is None or not hasattr(result, "boxes"):
        return ()
    
    height, width = result.orig_shape
    return tuple(
        PlateObservation(
            text="pending",
            confidence=float(box.conf[0]),
            bounding_box=_box(box.xyxy[0].tolist(), width, height),
        )
        for box in result.boxes
    )


def parse_pose_predictions(results: object) -> tuple[PoseObservation, ...]:
    result = _first_result (results)
    if result is None or not hasattr(result, "boxes"):
        return ()
    
    height, width = result.orig_shape
    keypoints = getattr(result, "keypoints", None)
    output: list[PoseObservation] = []
    for index, box in enumerate(result.boxes):
        points: list[PoseKeypoint] = []
        if keypoints is not None:
            point_set = keypoints[index]
            coordinates = point_set.xy[0].tolist()
            confidences = (
                point_set.conf[0].tolist()
                if getattr(point_set, "conf", None) is not None
                else [0.0] * len(coordinates)
            )
            for point_index, (coordinate, confidence) in enumerate(
                zip(coordinates, confidences, strict=False)
            ):
                points.append(
                    PoseKeypoint(
                        name=f"keypoint_{point_index}",
                        x=max(0.0, min(1.0, float(coordinate[0]) / width)),
                        y=max(0.0, min(1.0, float(coordinate[1]) / height)),
                        confidence=max(0.0, min(1.0, float(confidence))),
                    )
                )
        output.append(
            PoseObservation(
                posture="person",
                confidence=float(box.conf[0]),
                bounding_box=_box(box.xyxy[0].tolist(), width, height),
                keypoints=tuple(points),
            )
        )
    return tuple(output)

