# Detector Contract

Every production model must implement the `Detector` protocol from:

`ai-engine/detection/detector.py`

## Required properties

### identity

Returns immutable model metadata containing:

- Model name
- Model version
- Selected device
- Supported labels

### is_ready

Returns `True` when the detector is loaded and able to process frames.

A detector that is registered but not ready must return `False`.

## Required method

### detect(frame)

Input:

- Contiguous NumPy array
- Data type: `uint8`
- Colour format: BGR
- Shape: `(height, width, 3)`

Output:

- Tuple of `RawDetection` objects
- Bounding boxes in pixel coordinates
- Confidence values between `0` and `1`

## Detector responsibilities

A detector must:

- Load and manage its model runtime
- Return valid class IDs and labels
- Return pixel-coordinate bounding boxes
- Report readiness accurately
- Avoid modifying the submitted frame
- Raise a clear exception when inference fails

## Processor responsibilities

The detector must not:

- Decode uploaded files
- Apply HTTP validation
- Normalise bounding boxes
- Apply the client confidence threshold
- Construct API responses
- Manage correlation IDs