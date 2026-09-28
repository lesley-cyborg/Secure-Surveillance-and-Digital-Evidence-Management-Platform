import numpy as np
import pytest
from surveillance_addons.contracts import ThreatSignal
from surveillance_addons.pipeline import AnalysisPipeline

class Threat:
    is_ready = True
    def detect(self, frame):
        return (ThreatSignal(signal="weapon", confidence=0.9, source="weapon_model"),)

@pytest.mark.asyncio
async def test_pipeline_runs_optional_threat_model():
    result = await AnalysisPipeline(threat=Threat()).analyze(np.zeros((4, 4, 3), dtype=np.uint8))
    assert result.threat_signals[0].signal == "weapon"
