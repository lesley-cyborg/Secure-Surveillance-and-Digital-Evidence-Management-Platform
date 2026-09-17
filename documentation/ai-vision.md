# AI vision enrichments

The AI engine exposes `POST /api/v1/analyze/image` for object detection plus
optional OCR and face observations. OCR uses the locally installed Tesseract
binary through `pytesseract`; face detection uses OpenCV's frontal-face Haar
cascade. Both providers report readiness and degrade to an empty result when
their runtime is unavailable.

The response may contain `threat_signals`. These are evidence signals only
(for example, a `weapon` label from object detection). The backend's
`IncidentClassificationPolicy` remains the sole owner of incident type,
severity, priority, deduplication, and incident creation. The AI engine must
not emit those fields or create incidents.

Install the Python dependency with the AI engine requirements and install
Tesseract separately for OCR. The existing `/api/v1/detect/image` endpoint
and backend detection-event contract are unchanged.
