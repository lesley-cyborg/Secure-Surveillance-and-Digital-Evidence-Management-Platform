from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from time import monotonic

from addons.schemas import BoundingBox, PoseObservation


@dataclass(slots=True)
class _Track:
    box: BoundingBox
    posture: str
    history: deque[str]
    last_seen: float


@dataclass(slots=True)
class _CameraState:
    last_sequence: int = -1
    tracks: dict[int, _Track] = field(default_factory=dict)
    next_track_id: int = 0


class PoseConfirmation:
    """Confirm repeated pose observations by camera-local box association.

    Track keys are internal and are never exposed as identities. This is
    temporal detection confirmation, not person re-identification.
    """

    def __init__(
        self,
        *,
        required_frames: int = 3,
        expiry_seconds: float = 5.0,
        confidence_threshold: float = 0.75,
        minimum_iou: float = 0.3,
    ) -> None:
        if required_frames < 1:
            raise ValueError("required_frames must be at least 1")
        if expiry_seconds <= 0:
            raise ValueError("expiry_seconds must be positive")
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if not 0 <= minimum_iou <= 1:
            raise ValueError("minimum_iou must be between 0 and 1")
        self.required_frames = required_frames
        self.expiry_seconds = expiry_seconds
        self.confidence_threshold = confidence_threshold
        self.minimum_iou = minimum_iou
        self._cameras: dict[str, _CameraState] = {}
        self._lock = RLock()

    def update(
        self,
        camera_id: str,
        sequence_number: int,
        observations: tuple[PoseObservation, ...],
        *,
        now: float | None = None,
    ) -> tuple[PoseObservation, ...]:
        camera_key = camera_id.strip()
        if not camera_key:
            raise ValueError("camera_id cannot be empty")
        if sequence_number < 0:
            raise ValueError("sequence_number cannot be negative")
        timestamp = monotonic() if now is None else now

        with self._lock:
            state = self._cameras.setdefault(camera_key, _CameraState())
            # RTSP reconnects restart the source sequence; workers process one
            # frame at a time, so a decrease denotes a new sequence epoch.
            if state.last_sequence >= 0 and sequence_number < state.last_sequence:
                state.tracks.clear()
            elif sequence_number == state.last_sequence:
                return tuple(
                    observation.model_copy(update={"confirmed": False})
                    for observation in observations
                )
            state.last_sequence = sequence_number
            state.tracks = {
                track_id: track
                for track_id, track in state.tracks.items()
                if timestamp - track.last_seen <= self.expiry_seconds
            }

            pairs = sorted(
                (
                    (self._iou(observation.bounding_box, track.box), index, track_id)
                    for index, observation in enumerate(observations)
                    for track_id, track in state.tracks.items()
                    if (
                        self._iou(observation.bounding_box, track.box)
                        >= self.minimum_iou
                    )
                ),
                reverse=True,
            )
            matched_observations: set[int] = set()
            matched_tracks: set[int] = set()
            assignments: dict[int, int] = {}
            for _, observation_index, track_id in pairs:
                if (
                    observation_index not in matched_observations
                    and track_id not in matched_tracks
                ):
                    assignments[observation_index] = track_id
                    matched_observations.add(observation_index)
                    matched_tracks.add(track_id)

            updated: list[PoseObservation] = []
            next_tracks: dict[int, _Track] = {}
            for index, observation in enumerate(observations):
                assigned_track_id = assignments.get(index)
                track = (
                    state.tracks.get(assigned_track_id)
                    if assigned_track_id is not None
                    else None
                )
                if track is None:
                    track_id = state.next_track_id
                    state.next_track_id += 1
                    track = _Track(
                        box=observation.bounding_box,
                        posture=observation.posture,
                        history=deque(maxlen=self.required_frames),
                        last_seen=timestamp,
                    )
                elif track.posture != observation.posture:
                    track.history.clear()

                if observation.confidence >= self.confidence_threshold:
                    track.history.append(observation.posture)
                else:
                    track.history.clear()
                track.box = observation.bounding_box
                track.posture = observation.posture
                track.last_seen = timestamp
                next_tracks[track_id] = track
                updated.append(
                    observation.model_copy(
                        update={
                            "confirmed": (
                                observation.confidence >= self.confidence_threshold
                                and len(track.history) == self.required_frames
                            )
                        }
                    )
                )

            state.tracks = next_tracks
            return tuple(updated)

    def reset(self, camera_id: str | None = None) -> None:
        with self._lock:
            if camera_id is None:
                self._cameras.clear()
            else:
                self._cameras.pop(camera_id, None)

    @staticmethod
    def _iou(first: BoundingBox, second: BoundingBox) -> float:
        x_min = max(first.x_min, second.x_min)
        y_min = max(first.y_min, second.y_min)
        x_max = min(first.x_max, second.x_max)
        y_max = min(first.y_max, second.y_max)
        intersection = max(0.0, x_max - x_min) * max(0.0, y_max - y_min)
        first_area = (first.x_max - first.x_min) * (first.y_max - first.y_min)
        second_area = (second.x_max - second.x_min) * (second.y_max - second.y_min)
        union = first_area + second_area - intersection
        return intersection / union if union > 0 else 0.0
