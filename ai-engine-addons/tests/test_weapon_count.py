import numpy as np
import pytest
from surveillance_addons.contracts import ThreatSignal
from surveillance_addons.pipeline import AnalysisPipeline
class Threat:
    is_ready=True
    def detect(self, frame): return (ThreatSignal(signal="pistol",confidence=.9,source="model"),ThreatSignal(signal="person",confidence=.9,source="model"))
@pytest.mark.asyncio
async def test_weapon_count_only_counts_weapon_labels():
    result=await AnalysisPipeline(threat=Threat()).analyze(np.zeros((2,2,3),dtype=np.uint8))
    assert result.weapon_count==1
