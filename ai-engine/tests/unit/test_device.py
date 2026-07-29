from __future__ import annotations

import pytest

from detection.device import select_device
from detection.exceptions import (
    DeviceUnavailableError,
)
from detection.schemas import DeviceType


def test_cpu_device_is_always_available() -> None:
    selected = select_device(
        DeviceType.CPU,
        cuda_probe=lambda: False,
    )

    assert selected is DeviceType.CPU


def test_auto_falls_back_to_cpu() -> None:
    selected = select_device(
        DeviceType.AUTO,
        cuda_probe=lambda: False,
    )

    assert selected is DeviceType.CPU


def test_auto_selects_cuda_when_available() -> None:
    selected = select_device(
        DeviceType.AUTO,
        cuda_probe=lambda: True,
    )

    assert selected is DeviceType.CUDA


def test_explicit_cuda_fails_when_unavailable() -> None:
    with pytest.raises(DeviceUnavailableError):
        select_device(
            DeviceType.CUDA,
            cuda_probe=lambda: False,
        )
