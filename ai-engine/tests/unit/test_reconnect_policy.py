from __future__ import annotations

import asyncio
import math
from collections.abc import Iterator
from typing import Any

import pytest

from streaming.exceptions import (
    ReconnectAttemptsExhaustedError,
)
from streaming.reconnect_policy import (
    ReconnectPolicy,
    ReconnectPolicyConfig,
)


class SequenceRandomSource:
    def __init__(
        self,
        values: list[float],
    ) -> None:
        self._values: Iterator[float] = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(
        self,
        delay_seconds: float,
    ) -> None:
        self.delays.append(delay_seconds)


def test_policy_applies_bounded_exponential_backoff() -> None:
    policy = ReconnectPolicy(
        config=ReconnectPolicyConfig(
            initial_delay_seconds=0.5,
            multiplier=2.0,
            maximum_delay_seconds=2.0,
            jitter_ratio=0.0,
        )
    )

    decisions = [policy.next_delay() for _ in range(5)]

    assert [decision.base_delay_seconds for decision in decisions] == [
        0.5,
        1.0,
        2.0,
        2.0,
        2.0,
    ]

    assert [decision.delay_seconds for decision in decisions] == [
        0.5,
        1.0,
        2.0,
        2.0,
        2.0,
    ]


def test_policy_applies_symmetric_jitter() -> None:
    random_source = SequenceRandomSource(
        [
            0.0,
            0.5,
            1.0,
        ]
    )

    policy = ReconnectPolicy(
        config=ReconnectPolicyConfig(
            initial_delay_seconds=10.0,
            multiplier=1.0,
            maximum_delay_seconds=20.0,
            jitter_ratio=0.2,
        ),
        random_source=random_source,
    )

    lower = policy.next_delay()
    middle = policy.next_delay()
    upper = policy.next_delay()

    assert lower.jitter_seconds == pytest.approx(-2.0)
    assert lower.delay_seconds == pytest.approx(8.0)

    assert middle.jitter_seconds == pytest.approx(0.0)
    assert middle.delay_seconds == pytest.approx(10.0)

    assert upper.jitter_seconds == pytest.approx(2.0)
    assert upper.delay_seconds == pytest.approx(12.0)


def test_final_delay_does_not_exceed_maximum() -> None:
    policy = ReconnectPolicy(
        config=ReconnectPolicyConfig(
            initial_delay_seconds=10.0,
            multiplier=2.0,
            maximum_delay_seconds=10.0,
            jitter_ratio=0.5,
        ),
        random_source=lambda: 1.0,
    )

    decision = policy.next_delay()

    assert decision.base_delay_seconds == 10.0
    assert decision.jitter_seconds == 5.0
    assert decision.delay_seconds == 10.0


def test_policy_enforces_retry_limit() -> None:
    policy = ReconnectPolicy(
        config=ReconnectPolicyConfig(
            maximum_attempts=2,
            jitter_ratio=0.0,
        )
    )

    first = policy.next_delay()
    second = policy.next_delay()

    assert first.attempt_number == 1
    assert first.remaining_attempts == 1

    assert second.attempt_number == 2
    assert second.remaining_attempts == 0

    with pytest.raises(ReconnectAttemptsExhaustedError):
        policy.next_delay()

    snapshot = policy.snapshot()

    assert snapshot.exhausted is True
    assert snapshot.remaining_attempts == 0
    assert snapshot.next_base_delay_seconds is None


def test_zero_maximum_attempts_disables_retries() -> None:
    policy = ReconnectPolicy(config=ReconnectPolicyConfig(maximum_attempts=0))

    with pytest.raises(ReconnectAttemptsExhaustedError):
        policy.next_delay()

    snapshot = policy.snapshot()

    assert snapshot.attempts_made == 0
    assert snapshot.exhausted is True


def test_success_resets_attempts_and_schedule() -> None:
    policy = ReconnectPolicy(
        config=ReconnectPolicyConfig(
            initial_delay_seconds=1.0,
            multiplier=2.0,
            maximum_delay_seconds=10.0,
            jitter_ratio=0.0,
            maximum_attempts=4,
        )
    )

    first = policy.next_delay()
    second = policy.next_delay()

    assert first.delay_seconds == 1.0
    assert second.delay_seconds == 2.0

    policy.record_success()

    snapshot = policy.snapshot()

    assert snapshot.attempts_made == 0
    assert snapshot.remaining_attempts == 4
    assert snapshot.exhausted is False
    assert snapshot.last_delay_seconds is None
    assert snapshot.next_base_delay_seconds == 1.0

    after_success = policy.next_delay()

    assert after_success.attempt_number == 1
    assert after_success.delay_seconds == 1.0


async def test_wait_uses_calculated_delay() -> None:
    sleeper = RecordingSleeper()

    policy = ReconnectPolicy(
        config=ReconnectPolicyConfig(
            initial_delay_seconds=1.5,
            jitter_ratio=0.0,
        ),
        sleep=sleeper,
    )

    decision = await policy.wait()

    assert sleeper.delays == [
        1.5,
    ]
    assert decision.attempt_number == 1
    assert decision.delay_seconds == 1.5


async def test_wait_propagates_task_cancellation() -> None:
    sleep_started = asyncio.Event()
    never_finish = asyncio.Event()

    async def blocking_sleep(
        _: float,
    ) -> None:
        sleep_started.set()
        await never_finish.wait()

    policy = ReconnectPolicy(
        config=ReconnectPolicyConfig(jitter_ratio=0.0),
        sleep=blocking_sleep,
    )

    wait_task = asyncio.create_task(policy.wait())

    await sleep_started.wait()

    wait_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await wait_task

    snapshot = policy.snapshot()

    assert snapshot.attempts_made == 1


@pytest.mark.parametrize(
    (
        "configuration",
        "expected_message",
    ),
    [
        ({"initial_delay_seconds": 0.0}, "initial_delay_seconds"),
        ({"initial_delay_seconds": math.inf}, "initial_delay_seconds"),
        ({"multiplier": 0.9}, "multiplier"),
        ({"multiplier": math.nan}, "multiplier"),
        (
            {
                "initial_delay_seconds": 5.0,
                "maximum_delay_seconds": 4.0,
            },
            "maximum_delay_seconds",
        ),
        ({"jitter_ratio": -0.1}, "jitter_ratio"),
        ({"jitter_ratio": 1.1}, "jitter_ratio"),
        ({"maximum_attempts": -1}, "maximum_attempts"),
    ],
)
def test_config_rejects_invalid_values(
    configuration: dict[str, Any],
    expected_message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=expected_message,
    ):
        ReconnectPolicyConfig(**configuration)  


@pytest.mark.parametrize(
    "random_value",
    [
        -0.1,
        1.1,
        math.inf,
        -math.inf,
        math.nan,
    ],
)
def test_policy_rejects_invalid_random_values(
    random_value: float,
) -> None:
    policy = ReconnectPolicy(
        config=ReconnectPolicyConfig(),
        random_source=lambda: random_value,
    )

    with pytest.raises(
        ValueError,
        match="random source",
    ):
        policy.next_delay()
