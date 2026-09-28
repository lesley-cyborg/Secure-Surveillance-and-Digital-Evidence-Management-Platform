from __future__ import annotations
from pathlib import Path
from typing import Any, Callable
from .analysis_models import ModelIdentity
from .device import Device, select_device
from .integrity import validate_model_file
from .model_adapters import FrameArray
class ModelRuntimeAdapter:
    def __init__(self, *, name:str, version:str, model_path:Path, infer:Callable|None=None, parser:Callable|None=None, expected_sha256:str|None=None, requested_device:Device=Device.AUTO, cuda_available:bool=False, model_loader:Callable|None=None)->None:
        self._identity=ModelIdentity(name=name,version=version,path=Path(model_path),device="unselected"); self._expected_sha256=expected_sha256; self._requested_device=requested_device; self._cuda_available=cuda_available; self._infer=infer; self._parser=parser; self._model_loader=model_loader; self._model:Any=None; self._ready=False
    @property
    def identity(self)->ModelIdentity:return self._identity
    @property
    def model_path(self)->Path:return self._identity.path
    @property
    def expected_sha256(self)->str|None:return self._expected_sha256
    @property
    def is_ready(self)->bool:return self._ready
    def load(self, device:str|None=None)->None:
        validate_model_file(self.model_path,self._expected_sha256); selected=device or select_device(self._requested_device,self._cuda_available)
        if self._model_loader is not None:self._model=self._model_loader(self.model_path,selected)
        elif self._infer is None:
            try:
                from ultralytics import YOLO
            except ImportError as exc: raise RuntimeError("Ultralytics is required when no infer/model_loader is supplied") from exc
            self._model=YOLO(str(self.model_path))
        self._identity=ModelIdentity(name=self._identity.name,version=self._identity.version,path=self.model_path,device=selected); self._ready=True
    def warm_up(self)->None:
        if not self._ready: raise RuntimeError("model is not loaded")
        if self._model is not None and hasattr(self._model,"predict"):
            import numpy as np
            self._model.predict(source=np.zeros((32,32,3),dtype=np.uint8),device=self._identity.device,verbose=False)
    def unload(self)->None:self._model=None; self._ready=False
    def _predict(self,frame:FrameArray):
        if not self._ready: raise RuntimeError("model is not loaded")
        raw=self._infer(frame) if self._infer is not None else self._model.predict(source=frame,device=self._identity.device,verbose=False)
        return self._parser(raw) if self._parser is not None else raw
