# AI Engine

## Current purpose

`ai-engine/` is a separate production-oriented computer-vision service.

## Implemented components

### Detection

- detector interface
- schemas
- frame decoder
- frame processor
- model registry
- device selection
- inference concurrency gate

### Production model

`ai-engine/models/ultralytics_detector.py`

The repository contains an Ultralytics/YOLO detector adapter and a model artifact in the supplied archive.

The repository's `.gitignore` intends to exclude model weights, so do not reintroduce large model artifacts into version control.

### Lifecycle

`ai-engine/models/lifecycle.py`

handles model lifecycle concerns.

### Streaming

The streaming package includes:

- source abstraction
- OpenCV RTSP source
- frame queue
- frame sampler
- reconnect policy
- worker
- manager
- event dispatcher
- event serialization
- backend event sink

### API

FastAPI routes exist under:

`ai-engine/api/`

The API composition layer connects stream handling and result delivery.

## Detection classes

Project Phase 5.2 documentation identifies the initial target classes:

- Person
- Car
- Bus
- Truck
- Motorcycle
- Bicycle

Suspicious-object detection was intentionally deferred until the basic pipeline is stable/evaluated.

## Phase 5.2 progress

The progress document marks complete:

- real PNG submitted through API
- person detection
- vehicle detection
- normalized bounding boxes
- correlation-ID propagation
- model identity
- production model readiness
- CPU performance baseline

Still unchecked in the document:

- complete quality gate
- several CPU Docker hardening tasks
- final Phase 5.2 verification

Treat the progress file as the recorded status, but verify with tests/commands before claiming completion.

## Backend integration

The AI engine has backend authentication and incident sink integration.

The backend has:

`backend/app/modules/ai_ingestion/`

for receiving AI-generated events.
