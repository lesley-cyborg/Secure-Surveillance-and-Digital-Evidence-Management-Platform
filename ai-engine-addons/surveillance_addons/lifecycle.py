from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from .integrity import validate_model_file
from .device import Device, select_device

class LifecycleState(StrEnum): STOPPED="stopped"; LOADING="loading"; WARMING="warming"; READY="ready"; FAILED="failed"
@dataclass(slots=True)
class ModelLifecycle:
    model: object
    path: object
    expected_sha256: str | None=None
    requested_device: Device=Device.AUTO
    cuda_available: bool=False
    state: LifecycleState=LifecycleState.STOPPED
    last_error: str | None=None
    def startup(self) -> None:
        try:
            self.state=LifecycleState.LOADING; validate_model_file(self.path,self.expected_sha256)
            self.model.load(device=select_device(self.requested_device,self.cuda_available)); self.state=LifecycleState.WARMING; self.model.warm_up(); self.state=LifecycleState.READY; self.last_error=None
        except Exception as exc:
            self.state=LifecycleState.FAILED; self.last_error=type(exc).__name__; raise
    def shutdown(self) -> None:
        self.model.unload(); self.state=LifecycleState.STOPPED
