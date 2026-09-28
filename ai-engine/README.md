# Secure Surveillance AI Engine

FastAPI service for image analysis and live camera-stream detection. The
service combines object detection, optional OCR/face enrichments, RTSP workers,
and versioned detection-event delivery to the backend.

## Implemented integration

- `POST /api/v1/detect/image` runs object detection against an uploaded JPEG or
  PNG frame.
- `POST /api/v1/analyze/image` runs the same detection pipeline and returns
  optional Tesseract OCR text, OpenCV face observations, and threat signals.
  Threat signals are evidence only; incident classification belongs to the
  backend.
- `/api/v1/streams` registers, starts, stops, lists, and removes camera stream
  workers. Each stream has its own capture and detection tasks and carries
  camera/frame sequence context into detection events.
- The configured backend event sink serializes and dispatches detection events
  using schema `1.0` by default. Optional add-on analysis is attached only when
  `AI_ADDON_EVENT_V11_ENABLED=true`; this emits event schema `1.1`, which the
  backend validates and persists in contextual metadata. The image-detection
  contract is unchanged.
- OCR and face detection are optional capabilities. Missing OCR/Tesseract
  produces an empty `ocr` list and no OCR model descriptor; no placeholder or
  synthetic text is emitted. Expected Tesseract execution failures are logged
  without exposing OCR content and degrade the analysis result instead of
  failing the request.
- Optional live-stream add-ons (threat, plate, and pose detection) are disabled
  by default and run as a best-effort sidecar. Pose confirmation is per-camera,
  sequence-aware matching of repeated boxes; it is not person re-identification
  or fall classification. Plate text is included only when OCR recognizes
  text, and OCR failures degrade the capability without placeholder text or
  logging recognized values.

## Production model configuration

The engine does not download model weights. Place the model file on disk and
configure these `AI_`-prefixed environment variables:

| Variable | Purpose |
| --- | --- |
| `AI_PRODUCTION_MODEL_ENABLED` | Enables loading/registering the configured model. |
| `AI_MODEL_PATH` | Path to the local weights file (default `models/yolo26n.pt`). |
| `AI_MODEL_SHA256` | Required 64-character SHA-256 digest when production model loading is enabled. |
| `AI_MODEL_DEVICE` | `auto` (default), `cpu`, or `cuda`. `auto` chooses CUDA only when the installed PyTorch runtime reports it available and otherwise uses CPU; explicit unavailable CUDA fails model startup. |
| `AI_MODEL_CUDA_DEVICE_INDEX` | CUDA device index (default `0`). |
| `AI_ADDON_ENABLED` | Enables live stream add-on analysis (default `false`). |
| `AI_ADDON_EVENT_V11_ENABLED` | Emits analysis in event schema `1.1` (default `false`; requires add-ons enabled). |
| `AI_ADDON_THREAT_MODEL_ENABLED`, `AI_ADDON_PLATE_MODEL_ENABLED`, `AI_ADDON_POSE_MODEL_ENABLED` | Independently enable each local add-on model (all default `false`). |
| `AI_ADDON_THREAT_MODEL_PATH`, `AI_ADDON_PLATE_MODEL_PATH`, `AI_ADDON_POSE_MODEL_PATH` | Local weights paths for enabled add-on models. |
| `AI_ADDON_THREAT_MODEL_SHA256`, `AI_ADDON_PLATE_MODEL_SHA256`, `AI_ADDON_POSE_MODEL_SHA256` | Required 64-character SHA-256 digests for enabled add-on models. |
| `AI_ADDON_PLATE_OCR_ENABLED` | Enables plate OCR (default `true` when add-on analysis is enabled). |
| `AI_ADDON_POSE_CONFIRMATION_FRAMES` | Matched observations required for confirmation (default `3`). |
| `AI_ADDON_POSE_CONFIRMATION_EXPIRY_SECONDS` | Maximum age of a box match (default `5`). |
| `AI_ADDON_POSE_CONFIDENCE_THRESHOLD`, `AI_ADDON_POSE_MINIMUM_IOU` | Confidence and box-overlap thresholds (defaults `0.75` and `0.3`). |

The model adapter validates the file and digest before handing it to
Ultralytics. Runtime settings reject an enabled production model without a
digest, and the default production loader independently enforces the same
integrity check. Tests and development can still inject a custom model loader
without a real weights file or digest; this injection path is not used by the
production detector factory.

Tesseract is an optional system executable used by `pytesseract`; installing
the Python package alone does not install the executable. If it is unavailable,
the analysis API continues without OCR.

## Local setup and tests

From this directory, using Python 3.12 or 3.13:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,model]"
pytest -q tests/unit
pytest -q tests/integration/test_backend_event_delivery.py tests/integration/test_concurrent_streams.py
```

The real-RTSP tests additionally require the Docker test stack; see
`scripts/run_rtsp_integration.ps1`. No real model weights or CUDA device are
required for the unit or backend-event integration tests.
