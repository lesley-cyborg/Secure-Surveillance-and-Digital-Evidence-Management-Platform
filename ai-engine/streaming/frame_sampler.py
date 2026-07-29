from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

type MonotonicClock = Callable[[], float]


@dataclass(
    frozen=True,
    slots=True,
)
class FrameSamplerSnapshot:
    """Immutable view of frame-sampling statistics."""

    target_fps: float
    interval_seconds: float

    accepted_frames: int
    skipped_frames: int

    last_observed_at: float | None
    last_accepted_at: float | None
    next_due_at: float | None

    @property
    def observed_frames(self) -> int:
        """Return the total number of evaluated frames."""

        return self.accepted_frames + self.skipped_frames


class FrameSampler:
    """Monotonic fixed-rate frame sampler.

    The first observed frame is accepted immediately.

    Subsequent frames are accepted only when the next sampling
    deadline has been reached. Late frames advance the deadline
    along the original fixed-rate schedule to avoid timing drift.
    """

    def __init__(
        self,
        *,
        target_fps: float,
        clock: MonotonicClock = monotonic,
    ) -> None:
        if not math.isfinite(target_fps):
            raise ValueError("target_fps must be finite")

        if not 0 < target_fps <= 60:
            raise ValueError("target_fps must be between 0 and 60")

        self._target_fps = target_fps
        self._interval_seconds = 1.0 / target_fps
        self._clock = clock

        self._accepted_frames = 0
        self._skipped_frames = 0

        self._last_observed_at: float | None = None
        self._last_accepted_at: float | None = None
        self._next_due_at: float | None = None

        self._lock = Lock()

    @property
    def target_fps(self) -> float:
        return self._target_fps

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    def should_sample(self) -> bool:
        """Return whether the current frame should be published."""

        observed_at = float(self._clock())

        if not math.isfinite(observed_at):
            raise ValueError("monotonic clock must return a finite value")

        with self._lock:
            self._validate_clock_progression(observed_at)

            self._last_observed_at = observed_at

            if self._next_due_at is None:
                self._accept_first_frame(observed_at)
                return True

            if observed_at < self._next_due_at:
                self._skipped_frames += 1
                return False

            self._accept_due_frame(observed_at)

            return True

    def snapshot(
        self,
    ) -> FrameSamplerSnapshot:
        """Return current sampling counters and schedule."""

        with self._lock:
            return FrameSamplerSnapshot(
                target_fps=self._target_fps,
                interval_seconds=(self._interval_seconds),
                accepted_frames=(self._accepted_frames),
                skipped_frames=(self._skipped_frames),
                last_observed_at=(self._last_observed_at),
                last_accepted_at=(self._last_accepted_at),
                next_due_at=self._next_due_at,
            )

    def reset_schedule(self) -> None:
        """Restart scheduling while preserving counters.

        The next observed frame will be accepted immediately. This
        is useful after reconnecting a camera stream.
        """

        with self._lock:
            self._last_observed_at = None
            self._last_accepted_at = None
            self._next_due_at = None

    def reset(self) -> None:
        """Reset the schedule and all cumulative counters."""

        with self._lock:
            self._accepted_frames = 0
            self._skipped_frames = 0

            self._last_observed_at = None
            self._last_accepted_at = None
            self._next_due_at = None

    def _accept_first_frame(
        self,
        observed_at: float,
    ) -> None:
        self._accepted_frames += 1
        self._last_accepted_at = observed_at
        self._next_due_at = observed_at + self._interval_seconds

    def _accept_due_frame(
        self,
        observed_at: float,
    ) -> None:
        next_due_at = self._next_due_at

        if next_due_at is None:
            raise RuntimeError("Sampler deadline is not initialised")

        elapsed_after_deadline = observed_at - next_due_at

        elapsed_intervals = (
            math.floor(elapsed_after_deadline / self._interval_seconds) + 1
        )

        self._accepted_frames += 1
        self._last_accepted_at = observed_at

        # Advance from the previous deadline rather than from
        # observed_at. This preserves the original cadence and
        # prevents accumulated sampling drift.
        self._next_due_at = next_due_at + (elapsed_intervals * self._interval_seconds)

    def _validate_clock_progression(
        self,
        observed_at: float,
    ) -> None:
        if self._last_observed_at is not None and observed_at < self._last_observed_at:
            raise ValueError("monotonic clock moved backwards")
