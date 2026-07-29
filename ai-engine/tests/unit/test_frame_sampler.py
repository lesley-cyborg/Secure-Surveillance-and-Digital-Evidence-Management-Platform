from __future__ import annotations

import math

import pytest

from streaming.frame_sampler import (
    FrameSampler,
)


class FakeMonotonicClock:
    def __init__(
        self,
        initial_value: float = 0.0,
    ) -> None:
        self._value = initial_value

    def __call__(self) -> float:
        return self._value

    def set(
        self,
        value: float,
    ) -> None:
        self._value = value

    def advance(
        self,
        seconds: float,
    ) -> None:
        self._value += seconds


def test_first_frame_is_accepted_immediately() -> None:
    clock = FakeMonotonicClock(initial_value=100.0)

    sampler = FrameSampler(
        target_fps=2.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    snapshot = sampler.snapshot()

    assert snapshot.accepted_frames == 1
    assert snapshot.skipped_frames == 0
    assert snapshot.observed_frames == 1
    assert snapshot.last_accepted_at == 100.0
    assert snapshot.next_due_at == pytest.approx(100.5)


def test_frame_before_deadline_is_skipped() -> None:
    clock = FakeMonotonicClock()

    sampler = FrameSampler(
        target_fps=2.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    clock.advance(0.25)

    assert sampler.should_sample() is False

    snapshot = sampler.snapshot()

    assert snapshot.accepted_frames == 1
    assert snapshot.skipped_frames == 1
    assert snapshot.observed_frames == 2
    assert snapshot.next_due_at == pytest.approx(0.5)


def test_frame_at_deadline_is_accepted() -> None:
    clock = FakeMonotonicClock()

    sampler = FrameSampler(
        target_fps=2.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    clock.set(0.5)

    assert sampler.should_sample() is True

    snapshot = sampler.snapshot()

    assert snapshot.accepted_frames == 2
    assert snapshot.skipped_frames == 0
    assert snapshot.next_due_at == pytest.approx(1.0)


def test_late_frame_does_not_accumulate_drift() -> None:
    clock = FakeMonotonicClock()

    sampler = FrameSampler(
        target_fps=2.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    # The scheduled deadline is 0.5 seconds, but this frame arrives
    # late. The next deadline must remain 1.0, not become 1.24.
    clock.set(0.74)

    assert sampler.should_sample() is True
    assert sampler.snapshot().next_due_at == pytest.approx(1.0)

    clock.set(0.99)

    assert sampler.should_sample() is False

    clock.set(1.0)

    assert sampler.should_sample() is True
    assert sampler.snapshot().next_due_at == pytest.approx(1.5)


def test_multiple_missed_intervals_are_skipped() -> None:
    clock = FakeMonotonicClock()

    sampler = FrameSampler(
        target_fps=1.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    # Sampling deadlines would be 1.0 and 2.0. A frame received at
    # 2.6 is accepted, then the next aligned deadline becomes 3.0.
    clock.set(2.6)

    assert sampler.should_sample() is True

    snapshot = sampler.snapshot()

    assert snapshot.next_due_at == pytest.approx(3.0)
    assert snapshot.accepted_frames == 2


def test_sampler_tracks_accepted_and_skipped_frames() -> None:
    clock = FakeMonotonicClock()

    sampler = FrameSampler(
        target_fps=1.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    clock.set(0.2)
    assert sampler.should_sample() is False

    clock.set(0.7)
    assert sampler.should_sample() is False

    clock.set(1.0)
    assert sampler.should_sample() is True

    snapshot = sampler.snapshot()

    assert snapshot.accepted_frames == 2
    assert snapshot.skipped_frames == 2
    assert snapshot.observed_frames == 4
    assert snapshot.last_observed_at == 1.0
    assert snapshot.last_accepted_at == 1.0


def test_reset_schedule_accepts_next_frame_immediately() -> None:
    clock = FakeMonotonicClock()

    sampler = FrameSampler(
        target_fps=1.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    clock.set(0.25)
    assert sampler.should_sample() is False

    sampler.reset_schedule()

    clock.set(0.3)
    assert sampler.should_sample() is True

    snapshot = sampler.snapshot()

    # Cumulative metrics survive reconnection-style schedule resets.
    assert snapshot.accepted_frames == 2
    assert snapshot.skipped_frames == 1
    assert snapshot.next_due_at == pytest.approx(1.3)


def test_reset_clears_schedule_and_counters() -> None:
    clock = FakeMonotonicClock()

    sampler = FrameSampler(
        target_fps=1.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    clock.set(0.2)
    assert sampler.should_sample() is False

    sampler.reset()

    snapshot = sampler.snapshot()

    assert snapshot.accepted_frames == 0
    assert snapshot.skipped_frames == 0
    assert snapshot.observed_frames == 0
    assert snapshot.last_observed_at is None
    assert snapshot.last_accepted_at is None
    assert snapshot.next_due_at is None


@pytest.mark.parametrize(
    "target_fps",
    [
        0.0,
        -1.0,
        60.1,
        math.inf,
        -math.inf,
        math.nan,
    ],
)
def test_sampler_rejects_invalid_target_fps(
    target_fps: float,
) -> None:
    with pytest.raises(ValueError):
        FrameSampler(target_fps=target_fps)


def test_sampler_rejects_clock_regression() -> None:
    clock = FakeMonotonicClock(initial_value=10.0)

    sampler = FrameSampler(
        target_fps=1.0,
        clock=clock,
    )

    assert sampler.should_sample() is True

    clock.set(9.9)

    with pytest.raises(
        ValueError,
        match="moved backwards",
    ):
        sampler.should_sample()


@pytest.mark.parametrize(
    "clock_value",
    [
        math.inf,
        -math.inf,
        math.nan,
    ],
)
def test_sampler_rejects_non_finite_clock_values(
    clock_value: float,
) -> None:
    clock = FakeMonotonicClock(initial_value=clock_value)

    sampler = FrameSampler(
        target_fps=1.0,
        clock=clock,
    )

    with pytest.raises(
        ValueError,
        match="finite",
    ):
        sampler.should_sample()
