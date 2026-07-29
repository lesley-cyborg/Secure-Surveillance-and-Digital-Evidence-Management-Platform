from __future__ import annotations

import importlib
from collections.abc import Callable

from detection.exceptions import (
    DeviceUnavailableError,
)
from detection.schemas import DeviceType

CudaAvailabilityProbe = Callable[[], bool]


def is_cuda_available() -> bool:
    """
    Detect CUDA only when PyTorch is installed.

    Phase 5.1 does not require PyTorch, so a missing installation
    produces a normal CPU fallback rather than an import failure.
    """

    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return False

    cuda = getattr(
        torch,
        "cuda",
        None,
    )

    availability_check = getattr(
        cuda,
        "is_available",
        None,
    )

    if not callable(availability_check):
        return False

    return bool(availability_check())


def select_device(
    requested: DeviceType,
    *,
    cuda_probe: CudaAvailabilityProbe = (is_cuda_available),
) -> DeviceType:
    if requested is DeviceType.CPU:
        return DeviceType.CPU

    cuda_available = cuda_probe()

    if requested is DeviceType.AUTO:
        return DeviceType.CUDA if cuda_available else DeviceType.CPU

    if requested is DeviceType.CUDA:
        if not cuda_available:
            raise DeviceUnavailableError(
                "CUDA was explicitly requested but is not available"
            )

        return DeviceType.CUDA

    raise DeviceUnavailableError(f"Unsupported inference device: {requested}")
