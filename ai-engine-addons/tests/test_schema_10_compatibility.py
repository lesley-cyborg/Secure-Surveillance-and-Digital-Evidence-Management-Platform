from integration.compatibility_checks import validate_v10_payload, validate_v11_payload
def test_v10_payload_remains_valid_and_v11_is_additive():
    base={"schema_version":"1.0","detections":[],"detection_count":0}
    validate_v10_payload(base)
    extended={**base,"schema_version":"1.1","analysis":{"threat_signals":[],"plates":[],"poses":[],"degraded_capabilities":[]}}
    validate_v11_payload(extended)
    assert extended["detections"]==base["detections"]
