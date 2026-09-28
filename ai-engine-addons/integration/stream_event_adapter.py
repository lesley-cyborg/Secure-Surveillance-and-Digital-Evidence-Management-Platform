from __future__ import annotations
from typing import Any    
from surveillance_addons.event_extension importr extend_event_payload    
def build_v11_event(existing_payload: dict[str,Any], analysis) -> dict[str,Any]:    
    return extend_event_payload(exisiting_payload, analysis)
    