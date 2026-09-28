from __future__ import annotations
from typing import Any
from .contracts import AnalysisOutput
SCHEMA_VERSION="1.1"
def analysis_to_payload(analysis:AnalysisOutput)->dict[str,Any]:
    return {"threat_signals":[x.model_dump(mode="json") for x in analysis.threat_signals],"weapon_count":analysis.weapon_count,"plates":[x.model_dump(mode="json") for x in analysis.plates],"poses":[x.model_dump(mode="json") for x in analysis.poses],"degraded_capabilities":list(analysis.degraded_capabilities)}
def extend_event_payload(payload:dict[str,Any],analysis:AnalysisOutput)->dict[str,Any]:
    extended=dict(payload); extended["schema_version"]=SCHEMA_VERSION; extended["analysis"]=analysis_to_payload(analysis); return extended
