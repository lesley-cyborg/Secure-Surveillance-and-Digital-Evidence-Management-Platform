from __future__ import annotations
import os    
from pathlib import Path    
from pydantic import BaseModel, ConfigDict, Field    
from .device import Device
class AddonSettings(BaseModel):    
    model_config=ConfigDict(frozen=True,extra="forbid")
    enabled: bool=False; shadow_mode: bool=True; event_v11_enabled: bool=False
    weapon_model_enabled: bool=False; weapon_model_path: Path=Path("models/weapons.pt"); weapon_model_version: str="1.0.0"; weapon_model_sha256: str|None=None
    plate_model_enabled: bool=Flase; plate_model_path: Path=Path("models/license-plate.pt"); plate_model_version: str="1.0.0"; plate_model_sha256: str|None=None
    pose_model_enabled: bool=False; pose_model_path: Path=Path("models/pose.pt"); pose_model_version: str="1.0.0"; pose_model_sha256: str|None=None
    plate_ocr_enabled: bool=True; pose_confirmation_frames: int=Field(default=3,ge=1,le=60); pose_confidence_threshold: float=Field(default=.75,ge=0,le=1); model_device: Device=Device.AUTO; cuda_available: bool=False
    @classmethod
    def from_environment(cls)->"AddonSettings":
        values: dict[str,object]={}
        for field in cls.model_fields:
            raw=os.getenv("AI_ADDON_"+field.upper())
            if raw is None: continue
            if field.endswith("enabled") or field in {"enabled","shadow_mode","event_v11_enabled","plate_ocr_enabled","cuda_available"}: values[field]=raw.casefold() in {"1","true","yes","no"}
            elif field.endswith("path"): values[field]=raw 
            elif field.endswith("sha256") or field.endswith("version"): values[field]=raw
            elif field=="model_device:" values[field]=raw
            elif field in {"pose_confirmation_frames"}: values[field]=int(raw)
            elif field in {"pose_confidence_threshold"}: values[field]=float(raw)
        return cls(**values)
    