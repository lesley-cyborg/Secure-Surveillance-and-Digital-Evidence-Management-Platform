# AI Detection Engine Architecture

## Purpose

The AI detection engine provides a model-independent service for processing
surveillance images and returning structured object-detection results.

The engine separates image processing, model execution, API transport and
model registration so that production models can be replaced without changing
the public API contract.

## Main components

### API layer

Location:

`ai-engine/api/`

Responsibilities:

- Accept JPEG and PNG uploads
- Enforce upload limits
- Propagate correlation IDs
- Return detection results
- Map domain failures to HTTP responses
- Expose service and model health

### Frame decoder

Location:

`ai-engine/detection/frame_decoder.py`

Responsibilities:

- Decode JPEG and PNG payloads
- Verify media signatures
- Validate dimensions and byte sizes
- Convert grayscale and BGRA images to BGR
- Reject corrupt and unsupported images
- Produce frame metadata

### Detector interface

Location:

`ai-engine/detection/detector.py`

Responsibilities:

- Define the contract implemented by every detection model
- Expose model identity and health
- Accept a BGR NumPy frame
- Return pixel-coordinate detections

### Model registry

Location:

`ai-engine/detection/model_registry.py`

Responsibilities:

- Register detector implementations
- Manage multiple model versions
- Select default models
- Report model readiness
- Prevent duplicate registration

### Frame processor

Location:

`ai-engine/detection/frame_processor.py`

Responsibilities:

- Resolve the requested detector
- Decode image payloads
- Run model inference outside the event loop
- Apply confidence thresholds
- Normalise bounding boxes
- Measure inference duration
- Produce structured logs and correlation IDs

## Processing flow

1. A client submits an image through `/api/v1/detect/image`.
2. The API validates the content type and upload size.
3. The model registry resolves the selected detector.
4. The frame decoder validates and decodes the image.
5. The detector runs model inference.
6. The processor filters low-confidence detections.
7. Pixel bounding boxes are normalised.
8. The API returns a structured detection result.

## Public endpoints

- `GET /health`
- `GET /api/v1/models`
- `POST /api/v1/detect/image`

## Current limitation

Phase 5.1 uses fake detectors in tests and does not register a production
machine-learning model.

Phase 5.2 will add a production object-detection adapter.