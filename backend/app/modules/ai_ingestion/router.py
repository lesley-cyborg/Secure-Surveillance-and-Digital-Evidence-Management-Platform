from __future__ import annotations

import hashlib
import hmac
import re
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import JSONResponse

from app.core.config import (
    Settings,
    get_settings,
)
from app.modules.ai_ingestion.dependencies import (
    AIServiceAccess,
    DetectionEventIngestionServiceAccess,
)
from app.modules.ai_ingestion.schemas import (
    DetectionEventAcceptedResponse,
    DetectionEventIngestionRequest,
)
from app.modules.evidence.ai_bridge import (
    AIDetectionEventNotFoundError,
    AIDetectionIncidentMissingError,
    AIEvidenceArtifactCommand,
    AIEvidenceArtifactConflictError,
)
from app.modules.evidence.ai_http import (
    AIArtifactKind,
    AIEvidenceIngestionResponse,
    build_ai_artifact_filename,
    get_ai_artifact_contract,
)
from app.modules.evidence.dependencies import (
    AIDetectionEvidenceBridgeAccess,
)
from app.modules.evidence.errors import (
    EvidenceIngestionCompensationError,
    EvidenceStorageConfigurationError,
    EvidenceStorageError,
    EvidenceStorageIntegrityError,
    EvidenceStorageUnavailableError,
)

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

router = APIRouter(
    prefix="/internal/v1/ai",
    tags=["Internal AI ingestion"],
)

SettingsAccess = Annotated[
    Settings,
    Depends(get_settings),
]


@router.post(
    "/detection-events",
    response_model=DetectionEventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def ingest_detection_event(
    request: Request,
    event: DetectionEventIngestionRequest,
    principal: AIServiceAccess,
    ingestion_service: DetectionEventIngestionServiceAccess,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key"),
    ],
    correlation_id: Annotated[
        UUID,
        Header(alias="X-Correlation-ID"),
    ],
) -> DetectionEventAcceptedResponse:
    """Persist one authenticated AI detection event."""

    # Presence of this dependency performs service authentication.
    del principal

    if not _SHA256_HEX_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid idempotency key",
        )

    raw_body = await request.body()
    calculated_key = hashlib.sha256(raw_body).hexdigest()
    normalized_key = idempotency_key.casefold()

    if not hmac.compare_digest(
        calculated_key,
        normalized_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency key does not match the request body",
        )

    if event.event_id != correlation_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Correlation ID does not match the event ID",
        )

    result = await ingestion_service.ingest(
        event=event,
        idempotency_key=normalized_key,
    )

    return DetectionEventAcceptedResponse(
        event_id=result.source_event_id,
        correlation_id=correlation_id,
        duplicate=result.duplicate,
    )


@router.post(
    "/detection-events/{source_event_id}/evidence/{artifact_id}/{artifact_kind}",
    response_model=AIEvidenceIngestionResponse,
    include_in_schema=False,
    name="ingest_ai_detection_evidence",
)
async def ingest_ai_detection_evidence(
    request: Request,
    source_event_id: UUID,
    artifact_id: UUID,
    artifact_kind: AIArtifactKind,
    principal: AIServiceAccess,
    bridge: AIDetectionEvidenceBridgeAccess,
    settings: SettingsAccess,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key"),
    ],
    correlation_id: Annotated[
        UUID | None,
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> JSONResponse:
    """Ingest an AI key frame or event clip as forensic evidence."""

    # Presence of this dependency performs service authentication.
    del principal

    if not _SHA256_HEX_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "AI_EVIDENCE_INVALID_IDEMPOTENCY_KEY",
                "message": ("Idempotency-Key must be a 64-character hexadecimal SHA-256 digest."),
            },
        )

    contract = get_ai_artifact_contract(artifact_kind)

    supplied_content_type = (
        request.headers.get(
            "content-type",
            "",
        )
        .split(
            ";",
            maxsplit=1,
        )[0]
        .strip()
        .casefold()
    )

    if supplied_content_type != contract.mime_type.casefold():
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "AI_EVIDENCE_UNSUPPORTED_MEDIA_TYPE",
                "message": (f"{artifact_kind.value} requires Content-Type {contract.mime_type}."),
            },
        )

    raw_body = await _read_evidence_body(
        request=request,
        max_body_bytes=settings.ai_evidence_max_body_bytes,
    )

    if not raw_body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "AI_EVIDENCE_EMPTY_PAYLOAD",
                "message": "Evidence payload must not be empty.",
            },
        )

    calculated_digest = hashlib.sha256(raw_body).hexdigest()
    normalized_key = idempotency_key.casefold()

    if not hmac.compare_digest(
        calculated_digest,
        normalized_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "AI_EVIDENCE_IDEMPOTENCY_MISMATCH",
                "message": ("Idempotency-Key does not match the evidence body."),
            },
        )

    resolved_correlation_id = _resolve_correlation_id(
        request=request,
        supplied=correlation_id,
    )

    command = AIEvidenceArtifactCommand(
        source_event_id=source_event_id,
        artifact_id=artifact_id,
        evidence_type=contract.evidence_type,
        original_filename=build_ai_artifact_filename(
            artifact_id=artifact_id,
            contract=contract,
        ),
        mime_type=contract.mime_type,
        content=raw_body,
        correlation_id=str(resolved_correlation_id),
        source_ip=(request.client.host if request.client is not None else None),
        user_agent=request.headers.get("user-agent"),
        device_identifier="ai-engine",
    )

    try:
        result = await bridge.ingest(command=command)

    except AIDetectionEventNotFoundError as exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AI_EVIDENCE_DETECTION_NOT_FOUND",
                "message": str(exception),
            },
        ) from exception

    except AIDetectionIncidentMissingError as exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "AI_EVIDENCE_INCIDENT_MISSING",
                "message": str(exception),
            },
        ) from exception

    except AIEvidenceArtifactConflictError as exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "AI_EVIDENCE_ARTIFACT_CONFLICT",
                "message": str(exception),
            },
        ) from exception

    except EvidenceStorageConfigurationError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AI_EVIDENCE_STORAGE_CONFIGURATION_ERROR",
                "message": "Evidence storage is not available.",
            },
        ) from exception

    except EvidenceStorageUnavailableError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AI_EVIDENCE_STORAGE_UNAVAILABLE",
                "message": "Evidence storage is temporarily unavailable.",
            },
        ) from exception

    except EvidenceStorageIntegrityError as exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "AI_EVIDENCE_STORAGE_INTEGRITY_ERROR",
                "message": "Evidence storage integrity validation failed.",
            },
        ) from exception

    except EvidenceIngestionCompensationError as exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "AI_EVIDENCE_COMPENSATION_FAILED",
                "message": (
                    "Evidence ingestion failed and storage cleanup could not be completed."
                ),
            },
        ) from exception

    except EvidenceStorageError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AI_EVIDENCE_STORAGE_ERROR",
                "message": "Evidence storage is unavailable.",
            },
        ) from exception

    response = AIEvidenceIngestionResponse(
        evidence_id=result.evidence_id,
        evidence_number=result.evidence_number,
        source_event_id=result.source_event_id,
        artifact_id=result.artifact_id,
        duplicate=result.duplicate,
        correlation_id=resolved_correlation_id,
    )

    response_status = status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED

    return JSONResponse(
        status_code=response_status,
        content=response.model_dump(mode="json"),
        headers={
            "X-Correlation-ID": str(resolved_correlation_id),
            "X-Idempotency-Key": normalized_key,
            "X-Evidence-ID": str(result.evidence_id),
            "X-Artifact-ID": str(result.artifact_id),
        },
    )


def _resolve_correlation_id(
    *,
    request: Request,
    supplied: UUID | None,
) -> UUID:
    if supplied is not None:
        request.state.correlation_id = str(supplied)
        return supplied

    middleware_value = getattr(
        request.state,
        "correlation_id",
        None,
    )

    if isinstance(middleware_value, UUID):
        return middleware_value

    if isinstance(middleware_value, str):
        try:
            return UUID(middleware_value)
        except ValueError:
            pass

    resolved = uuid4()
    request.state.correlation_id = str(resolved)

    return resolved


async def _read_evidence_body(
    *,
    request: Request,
    max_body_bytes: int,
) -> bytes:
    if max_body_bytes <= 0:
        raise ValueError("max_body_bytes must be greater than zero")

    content_length = request.headers.get("content-length")

    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "AI_EVIDENCE_INVALID_CONTENT_LENGTH",
                    "message": "Content-Length must be a valid integer.",
                },
            ) from None

        if declared_length < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "AI_EVIDENCE_INVALID_CONTENT_LENGTH",
                    "message": "Content-Length must not be negative.",
                },
            )

        if declared_length > max_body_bytes:
            raise _payload_too_large()

    payload = bytearray()

    async for chunk in request.stream():
        if not chunk:
            continue

        if len(payload) + len(chunk) > max_body_bytes:
            raise _payload_too_large()

        payload.extend(chunk)

    return bytes(payload)


def _payload_too_large() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail={
            "code": "AI_EVIDENCE_PAYLOAD_TOO_LARGE",
            "message": "Evidence payload exceeds the configured limit.",
        },
    )
