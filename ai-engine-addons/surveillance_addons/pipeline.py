from __future__ import annotations
import asyncio
from collections.abc import Sequence
from typing import Any
from .contracts import AnalysisOutput, ThreatSignal
from .model_adapters import FrameArray, PlateAnalyzer, PoseDetector, ThreatDetector
from .plate_processing import read_plate
class AnalysisPipeline:
    def __init__(self,*,threat: ThreatDetector|None=None,plates:PlateAnalyzer|None=None,pose:PoseDetector|None=None,plate_ocr:Any=None): self.threat=threat; self.plates=plates; self.pose=pose; self.plate_ocr=plate_ocr
    async def _run_optional(self,name,operation):
        try:return name,await asyncio.to_thread(operation),None
        except Exception as exc:return name,(),type(exc).__name__
    async def analyze(self,frame:FrameArray,*,detections:Sequence[tuple[str,float]]=())->AnalysisOutput:
        jobs=[]; degraded[] 
        for name,adapter in (("threat",self.threat),("plates",self.plates),("pose",self.pose)):
            if adapter is None:continue
            if not adapter.is_ready:degraded.append(name);continue
            jobs.append(self._run_optional(name,lambda adapter=adapter:adapter.detect(frame)))
        results=await asyncio.gather(*jobs) if jobs else []; values={}
        for name,value,error in results: values[name]=value; degraded.extend([name] if error else [])
        known={"weapon","firearm","gun","pistol","rifle","knife"}; signals=list(values.get("threat",()))
        signals.extend(ThreatSignal(signal=l,confidence=c,source="object_detection") for l,c in detections if l.casefold() .replace(" ","_") in known)
        plates=list(values.get("plates", ()))
        if self.plate_ocr is not None and not getattr(
            self.plate_ocr,
            "is_ready",
            True,
        ):
            degraded.append("plate_ocr")
        elif self.plate_ocr is not None:
            enriched=[]
            for plate in plates:
                try:
                    text,confidence=await asyncio.to_thread(read_plate,frame,plate.bounding_box,self.plate_ocr.read)
                    if text.strip():enriched.append(plate.model_copy(update={"text":text.strip(),"confidence":max(0,min(1,confidence))}))
                except Exception:degraded.append("plate_ocr")
            plates=enriched
        count=sum(1 for signal in signals if signal.signal.signal.casefold() in known)
        return AnalysisOutput(threat_signals=tuple(signals),weapon_count=count,plates=tuple(plates),poses=tuple(values.get("pose",())),degraded_capabilities=tuple(sorted(set(degraded))))
















