from __future__ import annotations 
import logging
from surveillance_addons.contracts import AnalysisOutput
logger=logging.getLogger(__name__)    
def record_shadow_analysis(analysis: AnalysisOutput) -> None:    
    logger.info("addon_shadow_analysis",extra={"threat_count":len(analysis.threat_signals),"weapon_count":analysis.weapon_count,"plate_count":len(analysis.plates),"pose_count":len(analysis.poses),"degraded_capabilities":analysis.degraded_capabilities})