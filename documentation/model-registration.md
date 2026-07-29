# Model Registration

A detector must be registered with `ModelRegistry` before it can process
images.

## Example

```python
registry = ModelRegistry()

detector = ProductionDetector(
    model_path="models/security-model.onnx",
    device=DeviceType.CPU,
)

registry.register(
    detector,
    make_default=True,
    make_name_default=True,
)

