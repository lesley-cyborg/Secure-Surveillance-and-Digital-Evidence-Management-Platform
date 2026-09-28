from surveillance_addons.contracts import AnalysisOutput
from surveillance_addons.event_extension import SCHEMA_VERSION, extend_event_payload

def test_event_extension_is_additive():
    payload = extend_event_payload({"event_type": "camera.detection.completed"}, AnalysisOutput())
    assert payload["schema_version"] == SCHEMA_VERSION == "1.1"
    assert payload["event_type"] == "camera.detection.completed"
    assert "analysis" in payload
