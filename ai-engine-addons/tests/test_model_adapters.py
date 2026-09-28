from pathlib import Path
import numpy as np
from surveillance_addons.contracts import AnalysisOutput, ThreatSignal
from surveillance_addons.threat_detector import ThreatModelAdapter
def test_adapter_lifecycle_and_metadata(tmp_path: Path):
    model=tmp_path/"weapon.pt"; model.write_bytes(b"weights")
    adapter=ThreatModelAdapter(name="weapon",version="1.0",model_path=model,infer=lambda frame:(ThreatSignal(signal="weapon",confidence=.9,source="model"),),parser=lambda value:value)
    adapter.load(); assert adapter.is_ready and adapter.identity.name=="weapon"
    assert adapter.analyze(np.zeros((2,2,3),dtype=np.uint8)).threat_signals
    adapter.unload(); assert not adapter.is_ready
