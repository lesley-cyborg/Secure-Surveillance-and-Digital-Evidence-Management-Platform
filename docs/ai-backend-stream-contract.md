Field,AI sends (event_serialization),Backend accepts (DetectionEventIngestionRequest),Result
event_type,camera.detection.completed,"Literal[""camera.detection.completed""]",PASS
event_id,str(correlation_id),UUID,PASS
detections[],"class_id, label, confidence, bbox",DetectionPayload tuple,PASS
detection_count,len(detections),"int, must match list length",PASS
camera / model / timestamps,Present in payload builder (TypedDict),Present on request (same contract family),PASS (aligned by design)
ocr,Not serialized,Not in schema,N/A for stream
faces,Not serialized,Not in schema,N/A for stream
threat_signals,Not serialized,Not in schema,N/A for stream
incident severity / custody,Not sent,Not accepted from AI,PASS (correct boundary)

Concern,Status
HTTP POST to configured endpoint,PASS
Bearer + correlation + idempotency headers,PASS (auth module)
Retryable vs permanent status handling,PASS
"Endpoint validation (http/s, no creds in URL)",PASS

Stream / RTSP
    → StreamDetectionEvent
    → JSON (objects only)
    → POST /internal/v1/ai/...
    → DetectionEvent + backend incident classification
    → optional evidence via AI bridge

/api/v1/analyze/image
    → VisionAnalyzer (OCR + face + threat hints)
    → HTTP response to caller
    → does NOT automatically hit incident_sink

Choice,Meaning
A (recommended),Live pipeline = object detections only. Full vision = analyze/image for demos/tools.
B,"Extend stream JSON + backend schema for OCR/face/threat (more work, only if live UI needs it)."


# AI to Backend Stream Event Contract

## Overview
This document defines the strict serialization and ingestion contract between the AI Engine (continuous RTSP stream worker) and the Backend API. 

It establishes the boundary of what the AI produces, what it sends, and what the backend accepts and persists.

## Contract Matrix

The following table maps the exact fields in the `StreamDetectionEventPayload` (AI Engine) to the `DetectionEventIngestionRequest` (Backend Pydantic Schema).

| Field / Capability | AI Generates | AI Serializes | Backend Accepts | Backend Persists | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `schema_version` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `event_type` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `event_id` (UUID) | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `camera_id` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `frame.sequence_number` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `frame.captured_at` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `frame.received_at` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `model.name` / `version` / `device` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `detections` (array) | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `detection_count` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `inference.duration_ms` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `inference.processed_at` | ✓ | ✓ | ✓ | ✓ | **PASS** |
| `ocr` results | — | ✗ | ✗ | ✗ | **INTENTIONALLY OMITTED** |
| `faces` results | — | ✗ | ✗ | ✗ | **INTENTIONALLY OMITTED** |
| `threat_signals` | — | ✗ | ✗ | ✗ | **INTENTIONALLY OMITTED** |

## Architectural Decision: Separation of Concerns

The absence of `ocr`, `faces`, and `threat_signals` from this stream contract is **an intentional architectural design**, not an omission. The system maintains two distinct AI paths:

1. **Path 1: Continuous Stream Detection (This Contract)**
   - **Trigger**: RTSP video stream frames.
   - **Payload**: Lightweight object detection bounding boxes and inference metadata.
   - **Goal**: High-throughput, low-latency incident triggering and evidence bridging.

2. **Path 2: On-Demand Image Analysis**
   - **Trigger**: API request (`POST /api/v1/analyze/image`).
   - **Payload**: Rich vision analysis including OCR, facial recognition, and detailed threat signals.
   - **Goal**: Deep forensic analysis of specific frames or uploaded media.

Keeping the stream contract detection-centric prevents payload bloat, reduces network overhead, and maintains strict separation between *AI observation* (detection) and *backend decision* (incident classification).

## Security & Reliability Headers
Every HTTP request from the AI Engine to the Backend must include:
- `Authorization`: Bearer token for service-to-service authentication.
- `X-Correlation-ID`: UUID for distributed tracing across the pipeline.
- `Idempotency-Key`: SHA-256 hash of the deterministic JSON payload to guarantee exactly-once processing and prevent duplicate incidents/evidence on network retries.