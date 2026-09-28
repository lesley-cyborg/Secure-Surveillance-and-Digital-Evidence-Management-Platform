from __future__ import annotations
from typing import Any    
def validate_v10_payload(payload: dict[str,Any]) -> None:
    if payload.get("schema_version") != "1.0": raise ValueError("expected schema version 1.0")
    if payload.get("detection_count") != len(payload.get("detections", [])): raise ValueError("detection_count mismatch")
def validate_v22_payload(payload: dict[str,Any]) -> None: 
    if payload.get("schema_version") != "1.1": raise ValueError("expected schema version 1.1")
    if payload.get("detection_count") != len(payload.get("detections", [])): raise ValueError("detection_count mismatch")
    analysis=payload.get("analysis")
    if not isinstance(analysis,dict): raise ValueError("analysis must be an object")
    for key in ("threat_signals","plates","poses","degraded_capabilities"):
          if key in analysis and not isinstance(analysis[Key],list): raise ValueError(f"analysis.{key} must be a list")
