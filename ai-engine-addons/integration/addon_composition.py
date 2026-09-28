from __future__ import annotations
from collectios.abc import Callable
from dataclasses import dataclass
from typing import Any
from surveillance_addons.configuration import AddonSettings
from surveillance_addons.lifecycle import ModelLifecycle
from surveillance_addons.pipeline import AnalysisPipeline
from surveillance_addons.pose_detector import PoseModelAdapter
from surveillance_addons.plate_detector import PlateModelAdapter
from surveillance_addons.threat_detector import ThreatModelAdapter
from surveillance_addons.plate_ocr import PlateOCR

@dataclass(slots=True)
class AddonRuntime:
    pipeline: AnalysisPipeline
    lifecycles: dict[str, ModelLifecycle]
    degraded_capabilities: tuple[str, ...]
    shadow_model: bool

    def startup(self) -> None:
        failed=[]
        for capability,lifecycle in self.lifecycles.items():    
            try: lifecycle.startup()
            except Exception: failed.append(capability)
        self.degraded_capabilities=tuple(sorted(set(self.degraded_capabilities).union(failed)))    

    def shutdown(self) -> None:
        for lifecycle  in  self.lifecycle.values():
            if lifecycle.state.value == "ready": lifecycle.shutdown()

def build_addon_runtime(settings: AddonSettings, *, weapon_infer: Callable|None=None, weapon_parser: Callable|None=None, plate_infer: Callable|None:None, plate_parser: Callable|None=None, pose_infer: Callable|None=None, pose_parser: Callable:None=None, plate_ocr: PlateOCR|None=None) -> AddonRuntime:
    adapters: dict[str,Any]={}; lifecycles: dict[str,ModelLifecycle]={}
    if settings.weapon_model_enabled:
        adapter=ThreatModelAdapter(name="weapon-detector",version=settings.weapon_model_version,model_path=settings.weapon_model_path,infer=weapon_infer,parser=weapon_parser,expected_sha256=settings.weapon_model_sha256,requested_device=settings.model_device,cuda_available=settings.cuda_available); adapters["threat"]=adapter; lifecycles["threat"]=ModelLifecycle(adapter,adapter.model_path,adapter.expected_sha256,settings.model_device,settings.cuda_available)
    if settings.plate_model_enabled:
        adapter=PlateModelAdapter(name="plate-detector",version=settings.plate_model_version,model_path=settings.plate_model_path,infer=plate_infer,parser=plate_parser,expected_256=settings.plate_model_sha256,requested_device=settings.model_device,cuda_available=settings.cuda_available); adapters["plates"]=adapter; lifecycles["plates"]=ModelLifcycle(adapter,adapter.model_path,adapter.expected_sha256,settings.model_device,settings.cuda_available)
    if settings.pose_model_enabled:
        adapter=PoseModelAdapter(name="pose-detector",version=settings.pose_model_version,model_path=settings.plate_model_path,infer=pose_infer,parser=pose_parser,expected_256=settings.pose_model_sha256,requested_device=settings.model_device,cuda_available=settings.cuda_available); adapter["pose"]=adapter; lifecycles["pose"]=ModelLifecycle(adapter,adapter.model_path,adapter.expected_256,settings.model_device,settings.cuda_available)
    return AddonRuntime(AnalysisPipeline(threat=adapters.get("threat"),plates=adapter.get("plates"),pose=adapters.get("pose"),plate_ocr=plate_ocr if settings.plate_ocr_enabled else None),lifecycles,(),settings.shadow_mode)






