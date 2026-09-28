from __future__ import annotations
from enum import StrEnum

class Device(StrEnum):
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"

def select_device(requested: Device, cuda_available: bool) -> str:
    if requested is Device.CUDA and not cuda_available:
        raise RuntimeError("CUDA was requested but is unavailable")
    if requested is Device.AUTO:
        return "cuda" if cuda_available else "cpu"
    return requested.value
