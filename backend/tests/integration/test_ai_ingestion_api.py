from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID, uuid4

import httpx
from app.core.config import (
    Settings,
    get_settings,
)
from app.main import app
from app.modules.ai_ingestion.dependencies import (
    get_detection_event_ingestion_service,
)
from app.modules.ai_ingestion.schemas import (
    DetectionEventIngestionRequest,
)
from app.modules.ai_ingestion.service import (
    DetectionEventIngestionResult,
    DetectionEventIngestionService,
)
from pydantic import SecretStr

ENDPOINT = "/internal/v1/ai/detection-events"

SERVICE_TOKEN = "integration-ai-service-token"


class StubDetectionEventIngestionService:
    """In-memory persistence stub for AI-ingestion HTTP contract tests."""

    async def ingest(
        self,
        *,
        event: DetectionEventIngestionRequest,
        idempotency_key: str,
    ) -> DetectionEventIngestionResult:
        del idempotency_key

        return DetectionEventIngestionResult(
            persisted_event_id=event.event_id,
            source_event_id=event.event_id,
            duplicate=False,
        )


def create_stub_ingestion_service() -> DetectionEventIngestionService:
    return cast(
        DetectionEventIngestionService,
        StubDetectionEventIngestionService(),
    )


def create_settings(
    *,
    enabled: bool = True,
    token: str | None = SERVICE_TOKEN,
) -> Settings:
    configured_token = SecretStr(token) if token is not None else None

    return get_settings().model_copy(
        update={
            "ai_ingestion_enabled": enabled,
            "ai_ingestion_service_token": configured_token,
        }
    )


def create_payload(
    *,
    event_id: UUID | None = None,
    detection_count: int = 1,
    captured_at: str = "2026-08-01T00:00:00.123456Z",
    include_unknown_field: bool = False,
    schema_version: str = "1.0",
) -> dict[str, object]:
    resolved_event_id = event_id if event_id is not None else uuid4()

    payload: dict[str, object] = {
        "schema_version": schema_version,
        "event_type": "camera.detection.completed",
        "event_id": str(resolved_event_id),
        "camera_id": "camera-001",
        "frame": {
            "sequence_number": 42,
            "captured_at": captured_at,
            "received_at": "2026-08-01T00:00:00.133456Z",
        },
        "model": {
            "name": "surveillance-yolo",
            "version": "yolo26n-coco",
            "device": "cpu",
        },
        "detections": [
            {
                "class_id": 0,
                "label": "person",
                "confidence": 0.94,
                "bounding_box": {
                    "x_min": 0.1,
                    "y_min": 0.2,
                    "x_max": 0.8,
                    "y_max": 0.9,
                },
            }
        ],
        "detection_count": detection_count,
        "inference": {
            "duration_ms": 8.5,
            "processed_at": "2026-08-01T00:00:00.148456Z",
        },
    }

    if include_unknown_field:
        payload["unexpected_field"] = "must-be-rejected"

    if schema_version == "1.1":
        payload["analysis"] = {
            "threat_signals": [],
            "weapon_count": 0,
            "plates": [],
            "poses": [],
            "degraded_capabilities": ["plate_ocr"],
        }

    return payload


def encode_payload(
    payload: dict[str, object],
) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def create_headers(
    *,
    body: bytes,
    correlation_id: UUID,
    token: str = SERVICE_TOKEN,
    idempotency_key: str | None = None,
    include_authorization: bool = True,
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": (idempotency_key or hashlib.sha256(body).hexdigest()),
        "X-Correlation-ID": str(correlation_id),
    }

    if include_authorization:
        headers["Authorization"] = f"Bearer {token}"

    return headers


@asynccontextmanager
async def create_client(
    settings: Settings,
) -> AsyncIterator[httpx.AsyncClient]:
    """
    Create an ASGI client using the real FastAPI router/auth boundary while
    replacing only DetectionEvent persistence with an in-memory stub.
    """

    app.dependency_overrides[get_settings] = lambda: settings

    app.dependency_overrides[get_detection_event_ingestion_service] = create_stub_ingestion_service

    try:
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            yield client

    finally:
        app.dependency_overrides.pop(
            get_detection_event_ingestion_service,
            None,
        )

        app.dependency_overrides.pop(
            get_settings,
            None,
        )


async def test_disabled_ingestion_returns_503() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id)
    body = encode_payload(payload)

    async with create_client(create_settings(enabled=False)) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
            ),
        )

    assert response.status_code == 503

    assert response.json() == {"detail": "AI ingestion is unavailable"}


async def test_missing_configured_token_returns_503() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id)
    body = encode_payload(payload)

    async with create_client(create_settings(token=None)) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
            ),
        )

    assert response.status_code == 503

    assert response.json() == {"detail": "AI ingestion is unavailable"}


async def test_missing_bearer_token_returns_401() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id)
    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
                include_authorization=False,
            ),
        )

    assert response.status_code == 401

    assert response.headers["WWW-Authenticate"] == "Bearer"

    assert response.json() == {"detail": "Invalid service credentials"}


async def test_incorrect_bearer_token_returns_401() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id)
    body = encode_payload(payload)

    incorrect_token = "incorrect-service-token"

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
                token=incorrect_token,
            ),
        )

    assert response.status_code == 401

    assert SERVICE_TOKEN not in response.text
    assert incorrect_token not in response.text


async def test_valid_event_is_accepted() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id)
    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
            ),
        )

    assert response.status_code == 202

    assert response.json() == {
        "accepted": True,
        "duplicate": False,
        "event_id": str(event_id),
        "correlation_id": str(event_id),
    }


async def test_v11_event_with_analysis_is_accepted() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id, schema_version="1.1")
    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(body=body, correlation_id=event_id),
        )

    assert response.status_code == 202


async def test_v11_rejects_unreadable_plate_placeholder() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id, schema_version="1.1")
    payload["analysis"] = {
        "threat_signals": [],
        "weapon_count": 0,
        "plates": [
            {
                "text": "unreadable",
                "confidence": 0.0,
                "bounding_box": {
                    "x_min": 0.1,
                    "y_min": 0.1,
                    "x_max": 0.5,
                    "y_max": 0.4,
                },
            }
        ],
        "poses": [],
        "degraded_capabilities": [],
    }
    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(body=body, correlation_id=event_id),
        )

    assert response.status_code == 422


async def test_unknown_payload_field_is_rejected() -> None:
    event_id = uuid4()

    payload = create_payload(
        event_id=event_id,
        include_unknown_field=True,
    )

    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
            ),
        )

    assert response.status_code == 422


async def test_naive_timestamp_is_rejected() -> None:
    event_id = uuid4()

    payload = create_payload(
        event_id=event_id,
        captured_at="2026-08-01T00:00:00",
    )

    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
            ),
        )

    assert response.status_code == 422


async def test_detection_count_mismatch_is_rejected() -> None:
    event_id = uuid4()

    payload = create_payload(
        event_id=event_id,
        detection_count=2,
    )

    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
            ),
        )

    assert response.status_code == 422


async def test_unsupported_schema_version_is_rejected() -> None:
    event_id = uuid4()

    payload = create_payload(
        event_id=event_id,
        schema_version="2.0",
    )

    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
            ),
        )

    assert response.status_code == 422


async def test_invalid_idempotency_key_is_rejected() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id)
    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
                idempotency_key=("not-a-sha256-key"),
            ),
        )

    assert response.status_code == 422

    assert response.json() == {"detail": "Invalid idempotency key"}


async def test_body_hash_mismatch_is_rejected() -> None:
    event_id = uuid4()
    payload = create_payload(event_id=event_id)
    body = encode_payload(payload)

    incorrect_key = "0" * 64

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=event_id,
                idempotency_key=incorrect_key,
            ),
        )

    assert response.status_code == 422

    assert response.json() == {"detail": ("Idempotency key does not match the request body")}


async def test_correlation_id_mismatch_is_rejected() -> None:
    event_id = uuid4()
    different_correlation_id = uuid4()

    payload = create_payload(event_id=event_id)

    body = encode_payload(payload)

    async with create_client(create_settings()) as client:
        response = await client.post(
            ENDPOINT,
            content=body,
            headers=create_headers(
                body=body,
                correlation_id=(different_correlation_id),
            ),
        )

    assert response.status_code == 422

    assert response.json() == {"detail": ("Correlation ID does not match the event ID")}


def test_settings_repr_hides_service_token() -> None:
    secret_value = "never-display-ai-service-token"

    settings = create_settings(token=secret_value)

    representation = repr(settings)

    assert settings.ai_ingestion_service_token is not None

    assert settings.ai_ingestion_service_token.get_secret_value() == secret_value

    assert secret_value not in representation

    assert "ai_ingestion_service_token" not in representation
