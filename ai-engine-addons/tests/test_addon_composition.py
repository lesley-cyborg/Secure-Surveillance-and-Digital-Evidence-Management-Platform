from pathlib import Path
import numpy as np
from surveillance_addons.configuration import AddonSettings
from integration.addon_composition import build_addon_runtime
def test_runtime_loads_enabled_injected_model(tmp_path: Path):
    model=tmp_path/"weapon.pt"; model.write_bytes(b"weights")
    settings=AddonSettings(enabled=True,weapon_model_enabled=True,weapon_model_path=model,shadow_mode=True)
    runtime=build_addon_runtime(settings,weapon_infer=lambda frame:(),weapon_parser=lambda value:value)
    runtime.startup()
    assert runtime.lifecycles["threat"].state.value=="ready"
    runtime.shutdown()
