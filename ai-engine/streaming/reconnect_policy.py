from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from random import Random
from threading import Lock

from streaming.exceptions import (
    ReconnectAttemptsExhaustedError,
)

type RandomSource = Callable[[], float]
type SleepFunction = Callable[
    [float],
    Awaitable[None],
]


async def _default_sleep(
    delay_seconds: float,
) -> None:
    await asyncio.sleep(delay_seconds)


@dataclass(
    frozen=True,
    slots=True,
)
class ReconnectPolicyConfig:
    """Immutable configuration for reconnect scheduling."""

    initial_delay_seconds: float = 1.0
    multiplier: float = 2.0
    maximum_delay_seconds: float = 30.0
    jitter_ratio: float = 0.2

    # None means retry indefinitely. Zero disables retries.
    maximum_attempts: int | None = None

    def __post_init__(self) -> None:
        self._validate_finite_positive(
            self.initial_delay_seconds,
            field_name="initial_delay_seconds",
        )
        self._validate_finite_positive(
            self.maximum_delay_seconds,
            field_name="maximum_delay_seconds",
        )

        if not math.isfinite(self.multiplier):
            raise ValueError("multiplier must be finite")

        if self.multiplier < 1:
            raise ValueError("multiplier must be at least 1")

        if self.maximum_delay_seconds < self.initial_delay_seconds:
            raise ValueError(
                "maximum_delay_seconds cannot be less than initial_delay_seconds"
            )

        if not math.isfinite(self.jitter_ratio):
            raise ValueError("jitter_ratio must be finite")

        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

        if self.maximum_attempts is not None and self.maximum_attempts < 0:
            raise ValueError("maximum_attempts cannot be negative")

    @staticmethod
    def _validate_finite_positive(
        value: float,
        *,
        field_name: str,
    ) -> None:
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must be finite")

        if value <= 0:
            raise ValueError(f"{field_name} must be positive")


@dataclass(
    frozen=True,
    slots=True,
)
class ReconnectDecision:
    """One scheduled reconnect attempt."""

    attempt_number: int

    base_delay_seconds: float
    jitter_seconds: float
    delay_seconds: float

    remaining_attempts: int | None


@dataclass(
    frozen=True,
    slots=True,
)
class ReconnectPolicySnapshot:
    """Read-only policy state."""

    attempts_made: int
    maximum_attempts: int | None
    remaining_attempts: int | None

    exhausted: bool

    next_base_delay_seconds: float | None
    last_delay_seconds: float | None


class ReconnectPolicy:
    """Bounded exponential reconnect policy with jitter.

    Attempt delays follow the configured exponential schedule:

        initial
        initial * multiplier
        initial * multiplier²
        ...

    The base delay is capped at maximum_delay_seconds. Proportional
    jitter is then applied and the final delay is capped again.
    """

    def __init__(
        self,
        *,
        config: ReconnectPolicyConfig,
        random_source: RandomSource | None = None,
        sleep: SleepFunction | None = None,
    ) -> None:
        self._config = config

        random_generator = Random()

        self._random_source = (
            random_source if random_source is not None else random_generator.random
        )
        self._sleep = sleep if sleep is not None else _default_sleep

        self._attempts_made = 0
        self._next_base_delay_seconds = config.initial_delay_seconds
        self._last_delay_seconds: float | None = None

        self._lock = Lock()

    @property
    def config(self) -> ReconnectPolicyConfig:
        return self._config

    def next_delay(self) -> ReconnectDecision:
        """Reserve and return the next reconnect attempt."""

        with self._lock:
            if self._is_exhausted_unlocked():
                raise ReconnectAttemptsExhaustedError(
                    "Reconnect attempt limit has been reached"
                )

            base_delay_seconds = self._next_base_delay_seconds

            random_value = float(self._random_source())
            self._validate_random_value(random_value)

            jitter_limit = base_delay_seconds * self._config.jitter_ratio
            jitter_seconds = ((random_value * 2.0) - 1.0) * jitter_limit

            delay_seconds = min(
                self._config.maximum_delay_seconds,
                max(
                    0.0,
                    base_delay_seconds + jitter_seconds,
                ),
            )

            self._attempts_made += 1
            attempt_number = self._attempts_made
            self._last_delay_seconds = delay_seconds

            self._next_base_delay_seconds = min(
                self._config.maximum_delay_seconds,
                base_delay_seconds * self._config.multiplier,
            )

            return ReconnectDecision(
                attempt_number=attempt_number,
                base_delay_seconds=(base_delay_seconds),
                jitter_seconds=jitter_seconds,
                delay_seconds=delay_seconds,
                remaining_attempts=(self._remaining_attempts_unlocked()),
            )

    async def wait(self) -> ReconnectDecision:
        """Wait until the next reconnect attempt is due.

        Task cancellation is intentionally allowed to propagate
        through the underlying asynchronous sleep.
        """

        decision = self.next_delay()

        await self._sleep(decision.delay_seconds)

        return decision

    def record_success(self) -> None:
        """Reset retry state after a successful connection."""

        self.reset()

    def reset(self) -> None:
        """Reset retry attempts and the exponential schedule."""

        with self._lock:
            self._attempts_made = 0
            self._next_base_delay_seconds = self._config.initial_delay_seconds
            self._last_delay_seconds = None

    def snapshot(self) -> ReconnectPolicySnapshot:
        """Return current retry counters and schedule."""

        with self._lock:
            exhausted = self._is_exhausted_unlocked()

            return ReconnectPolicySnapshot(
                attempts_made=self._attempts_made,
                maximum_attempts=(self._config.maximum_attempts),
                remaining_attempts=(self._remaining_attempts_unlocked()),
                exhausted=exhausted,
                next_base_delay_seconds=(
                    None if exhausted else self._next_base_delay_seconds
                ),
                last_delay_seconds=(self._last_delay_seconds),
            )

    def _is_exhausted_unlocked(self) -> bool:
        maximum_attempts = self._config.maximum_attempts

        return maximum_attempts is not None and self._attempts_made >= maximum_attempts

    def _remaining_attempts_unlocked(
        self,
    ) -> int | None:
        maximum_attempts = self._config.maximum_attempts

        if maximum_attempts is None:
            return None

        return max(
            0,
            maximum_attempts - self._attempts_made,
        )

    @staticmethod
    def _validate_random_value(
        value: float,
    ) -> None:
        if not math.isfinite(value):
            raise ValueError("random source must return a finite value")

        if not 0 <= value <= 1:
            raise ValueError("random source must return a value between 0 and 1")
