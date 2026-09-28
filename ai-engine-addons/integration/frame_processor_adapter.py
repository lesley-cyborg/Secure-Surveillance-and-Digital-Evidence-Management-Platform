from __future__ import annotations
from typing import Any    
from surveillance_addons.pipeline import AnalysisPipeline    
class AddonFrameProcessor:    
    """Narrow opt-in boundary; the host FrameProcessor remains untouched."""
    def __init__(self, pipeline: AnalysisPipeline): self.pipeline=pipeline
    async def enrich(self, frame, existing_detections=()):
        return await self.pipeline.analysis(frame, detections=existing_detections)
    