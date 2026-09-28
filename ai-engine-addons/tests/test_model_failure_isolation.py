import numpy as np
import pytest
from surveillance_addons.pipeline import AnalysisPipeline
class Broken:
    is_ready=True
    def detect(self, frame): raise RuntimeError("boom")
@pytest.mark.asyncio
async def test_broken_optional_model_isolated():
    result=await AnalysisPipeline(threat=Broken()).analyze(np.zeros((2,2,3),dtype=np.uint8))
    assert result.degraded_capabilities == ("threat",)
