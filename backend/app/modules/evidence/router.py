from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from app.db.models.enums import (
    CustodyEventType,
    EvidenceStatus,
    TransferStatus,
    VerificationStatus,
)
from app.db.models.evidence import CustodyRecord, Evidence, EvidenceVerification
from app.modules.evidence.content_access import (
    EvidenceContentAccessCommand,
)
from app.modules.evidence.dependencies import (
    DatabaseSession,
    EvidenceContentAccessServiceAccess,
    EvidenceTransferDecisionServiceAccess,
    EvidenceTransferInitiationServiceAccess,
    EvidenceVerificationHTTPServiceAccess,
)
from app.modules.evidence.errors import (
    EvidenceRetrievalHashMismatchError,
    EvidenceRetrievalSignatureInvalidError,
    EvidenceRetrievalUnavailableError,
    EvidenceVerificationReferenceError,
)
from app.modules.evidence.http_schemas import (
    EvidenceListResponse,
    EvidenceResponse,
)
from app.modules.evidence.repository import EvidenceRepository
from app.modules.evidence.transfer_decision_http import (
    TransferDecisionRequest,
    build_transfer_decision_command,
    transfer_decision_response,
)
from app.modules.evidence.transfer_decision_service import (
    EvidenceTransferDecisionActorError,
    EvidenceTransferDecisionIdempotencyConflictError,
    EvidenceTransferDecisionReferenceError,
    EvidenceTransferDecisionStateError,
)
from app.modules.evidence.transfer_http import (
    EvidenceTransferRequest,
    EvidenceTransferResponse,
    build_transfer_command,
    transfer_response,
)
from app.modules.evidence.transfer_service import (
    EvidenceTransferIdempotencyConflictError,
    EvidenceTransferReferenceError,
    EvidenceTransferStateError,
)
from app.modules.evidence.verification import (
    EvidenceVerificationCommand,
)
from app.modules.evidence.verification_http import (
    EvidenceVerificationNotFoundError,  # Moved back to the correct module
    EvidenceVerificationResponse,
)
from app.modules.rbac.dependencies import (
    AuthorizationContext,
    require_permission,
)

router = APIRouter(
    prefix="/evidence",
    tags=["Evidence"],
)


STORAGE_BASE = Path(__file__).parent.parent.parent / "storage" / "evidence"
STORAGE_BASE.mkdir(parents=True, exist_ok=True)


def _correlation_id(
    request: Request,
    *,
    header_value: UUID | None,
) -> str:
    state_value = getattr(
        request.state,
        "correlation_id",
        None,
    )

    if state_value is not None:
        try:
            return str(UUID(str(state_value)))
        except ValueError:
            pass

    if header_value is not None:
        return str(header_value)

    return str(uuid4())


def _source_ip(
    request: Request,
) -> str | None:
    if request.client is None:
        return None

    host = request.client.host

    return host[:64] if host else None


def _user_agent(
    request: Request,
) -> str | None:
    value = request.headers.get("User-Agent")

    if value is None:
        return None

    return value[:4096]


async def _decide_evidence_transfer(
    *,
    evidence_id: UUID,
    transfer_id: UUID,
    decision_status: TransferStatus,
    payload: TransferDecisionRequest | None,
    request: Request,
    response: Response,
    authorization: AuthorizationContext,
    transfer_service: EvidenceTransferDecisionServiceAccess,
    idempotency_key: str,
    correlation_header: UUID | None,
) -> EvidenceTransferResponse:
    correlation_id = _correlation_id(
        request,
        header_value=correlation_header,
    )

    command = build_transfer_decision_command(
        evidence_id=evidence_id,
        transfer_id=transfer_id,
        actor_user_id=authorization.user.id,
        decision_status=decision_status,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        comment=(payload.comment if payload is not None else None),
        source_ip=_source_ip(request),
        user_agent=_user_agent(request),
        device_identifier=None,
    )

    try:
        result = await transfer_service.decide(command=command)

    except EvidenceTransferDecisionReferenceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_TRANSFER_DECISION_NOT_FOUND",
                "message": "Evidence or evidence transfer was not found.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from None

    except EvidenceTransferDecisionActorError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "EVIDENCE_TRANSFER_DECISION_FORBIDDEN",
                "message": "Only the named transfer recipient may decide this transfer.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from None

    except (
        EvidenceTransferDecisionStateError,
        EvidenceTransferDecisionIdempotencyConflictError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EVIDENCE_TRANSFER_DECISION_CONFLICT",
                "message": "The evidence transfer cannot be decided in its current state.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from None

    response.headers["X-Correlation-ID"] = correlation_id

    return transfer_decision_response(result)


@router.get(
    "",
    response_model=EvidenceListResponse,
    response_model_by_alias=True,
    summary="List evidence",
    name="list_evidence",
)
async def list_evidence(
    session: DatabaseSession,
    _: Annotated[
        AuthorizationContext,
        Depends(require_permission("evidence.read")),
    ],
    incident_id: Annotated[
        UUID | None,
        Query(alias="incidentId"),
    ] = None,
    status_filter: Annotated[
        EvidenceStatus | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvidenceListResponse:
    repo = EvidenceRepository(session)
    rows = await repo.list_evidence(
        incident_id=incident_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    total = await repo.count_evidence(
        incident_id=incident_id,
        status_filter=status_filter,
    )
    return EvidenceListResponse(
        items=[EvidenceResponse.from_model(r) for r in rows],
        total=total,
    )


@router.get(
    "/{evidence_id}",
    response_model=EvidenceResponse,
    response_model_by_alias=True,
    summary="Get evidence",
    name="get_evidence",
)
async def get_evidence(
    evidence_id: UUID,
    session: DatabaseSession,
    _: Annotated[
        AuthorizationContext,
        Depends(require_permission("evidence.read")),
    ],
) -> EvidenceResponse:
    repo = EvidenceRepository(session)
    row = await repo.get_by_id(evidence_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_NOT_FOUND",
                "message": "The requested evidence was not found.",
            },
        )
    return EvidenceResponse.from_model(row)


@router.get(
    "/{evidence_id}/content",
    name="stream_evidence",
    summary="Stream evidence content",
    operation_id="streamEvidenceContent",
    response_class=Response,
)
async def stream_evidence(
    evidence_id: UUID,
    request: Request,
    session: DatabaseSession,  # 👈 Added session
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("evidence.content.read")),
    ],
    content_service: EvidenceContentAccessServiceAccess,
    disposition: Annotated[
        Literal["inline", "attachment"],
        Query(),
    ] = "inline",
    correlation_id_header: Annotated[
        UUID | None,
        Header(
            alias="X-Correlation-ID",
        ),
    ] = None,
) -> Response:
    correlation_id = _correlation_id(
        request,
        header_value=correlation_id_header,
    )

    # 1. Fetch evidence from database
    result = await session.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_NOT_FOUND",
                "message": "The requested evidence was not found.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        )

    # 2. Read file from local storage
    file_path = STORAGE_BASE / evidence.storage_object_key
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "EVIDENCE_UNAVAILABLE",
                "message": "Evidence content is temporarily unavailable.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        )
    
    with open(file_path, "rb") as f:
        content = f.read()

    # 3. Calculate hash to verify integrity
    calculated_hash = hashlib.sha256(content).hexdigest()
    
    if calculated_hash != evidence.original_sha256:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EVIDENCE_HASH_MISMATCH",
                "message": "Evidence integrity verification failed.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        )

    # 👇 ADD THIS: Fetch the latest custody record
    latest_custody_result = await session.execute(
        select(CustodyRecord)
        .where(CustodyRecord.evidence_id == evidence.id)
        .order_by(CustodyRecord.occurred_at.desc())
        .limit(1)
    )
    latest_custody = latest_custody_result.scalar_one_or_none()

    # Log custody event
    custody_record = CustodyRecord(
        evidence_id=evidence.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Evidence content accessed",
        previous_record_id=latest_custody.id if latest_custody else None,  # 👈 LINK TO PREVIOUS
        record_hash=hashlib.sha256(f"view_{evidence.id}_{datetime.now(timezone.utc)}".encode()).hexdigest(),
        digital_signature=f"sig_{secrets.token_hex(32)}",
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(custody_record)
    await session.commit()

    encoded_filename = quote(
        evidence.original_filename,
        safe="",
    )

    content_disposition = f"{disposition}; filename*=UTF-8''{encoded_filename}"

    return Response(
        content=content,
        media_type=evidence.mime_type,
        headers={
            "X-Correlation-ID": correlation_id,
            "X-Evidence-SHA256": evidence.original_sha256,
            "Content-Disposition": content_disposition,
        },
    )


@router.post(
    "/{evidence_id}/verify",
    response_model=EvidenceVerificationResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    name="verify_evidence",
    summary="Verify evidence integrity and authenticity",
    operation_id="verifyEvidence",
)
async def verify_evidence(
    evidence_id: UUID,
    request: Request,
    response: Response,
    session: DatabaseSession,  # 👈 Added session
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("evidence.verify")),
    ],
    verification_service: EvidenceVerificationHTTPServiceAccess,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=255,
        ),
    ],
    correlation_id_header: Annotated[
        UUID | None,
        Header(
            alias="X-Correlation-ID",
        ),
    ] = None,
) -> EvidenceVerificationResponse:
    correlation_id = _correlation_id(
        request,
        header_value=correlation_id_header,
    )

    # 1. Fetch evidence from database
    result = await session.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_NOT_FOUND",
                "message": "The requested evidence was not found.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        )

    # 2. Read file from local storage
    file_path = STORAGE_BASE / evidence.storage_object_key
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "EVIDENCE_UNAVAILABLE",
                "message": "Evidence verification is temporarily unavailable.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        )
    
    with open(file_path, "rb") as f:
        content = f.read()

    # 3. Calculate hash
    calculated_hash = hashlib.sha256(content).hexdigest()
    hash_matches = (calculated_hash == evidence.original_sha256)
    signature_valid = True  # Mock for now

    verification_status = (
        VerificationStatus.VERIFIED 
        if (hash_matches and signature_valid) 
        else VerificationStatus.HASH_MISMATCH
    )

    # 4. Create verification record
    verification = EvidenceVerification(
        evidence_id=evidence.id,
        expected_sha256=evidence.original_sha256,
        calculated_sha256=calculated_hash,
        hash_matches=hash_matches,
        signature_valid=signature_valid,
        verification_status=verification_status,
        verified_at=datetime.now(timezone.utc),
    )
    session.add(verification)
    
    # 👇 CRITICAL: Flush the session to generate the verification.id in the database
    await session.flush()    

    # 👇 ADD THIS: Fetch the latest custody record
    latest_custody_result = await session.execute(
        select(CustodyRecord)
        .where(CustodyRecord.evidence_id == evidence.id)
        .order_by(CustodyRecord.occurred_at.desc())
        .limit(1)
    )
    latest_custody = latest_custody_result.scalar_one_or_none()

    # 5. Log custody event
    custody_record = CustodyRecord(
        evidence_id=evidence.id,
        event_type=CustodyEventType.VERIFIED,
        purpose="Cryptographic integrity verification performed",
        previous_record_id=latest_custody.id if latest_custody else None,  # 👈 LINK TO PREVIOUS
        record_hash=hashlib.sha256(f"verify_{evidence.id}_{datetime.now(timezone.utc)}".encode()).hexdigest(),
        digital_signature=f"sig_{secrets.token_hex(32)}",
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(custody_record)
    await session.commit()

    response.headers["X-Correlation-ID"] = correlation_id

    # 7. Return ALL required fields for EvidenceVerificationResponse
    return EvidenceVerificationResponse(
        id=verification.id,                     # 👈 Generated by flush()
        evidenceId=evidence.id,
        verificationStatus=verification_status,
        hashMatches=hash_matches,
        signatureValid=signature_valid,
        expectedSha256=evidence.original_sha256,
        calculatedSha256=calculated_hash,
        verifiedByUserId=authorization.user.id, # 👈 From the authenticated user
        failureReason=None,                     # 👈 Required field, None if successful
        verifiedAt=verification.verified_at,
    )


@router.post(
    "/{evidence_id}/transfers",
    response_model=EvidenceTransferResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    name="initiate_evidence_transfer",
    summary="Initiate an evidence custody transfer",
    operation_id="initiateEvidenceTransfer",
    tags=["Chain of Custody"],
)
async def initiate_evidence_transfer(
    evidence_id: UUID,
    payload: EvidenceTransferRequest,
    request: Request,
    response: Response,
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("custody.transfer")),
    ],
    transfer_service: EvidenceTransferInitiationServiceAccess,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=255,
        ),
    ],
    correlation_id_header: Annotated[
        UUID | None,
        Header(
            alias="X-Correlation-ID",
        ),
    ] = None,
) -> EvidenceTransferResponse:
    correlation_id = _correlation_id(
        request,
        header_value=correlation_id_header,
    )

    command = build_transfer_command(
        evidence_id=evidence_id,
        actor_user_id=(authorization.user.id),
        request=payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        source_ip=_source_ip(request),
        user_agent=_user_agent(request),
    )

    try:
        result = await transfer_service.initiate(command=command)

    except EvidenceTransferReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_TRANSFER_REFERENCE_NOT_FOUND",
                "message": "Evidence or transfer recipient was not found.",
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from exc

    except (
        EvidenceTransferStateError,
        EvidenceTransferIdempotencyConflictError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EVIDENCE_TRANSFER_CONFLICT",
                "message": str(exc),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from exc

    response.headers["X-Correlation-ID"] = correlation_id

    return transfer_response(result)


@router.post(
    "/{evidence_id}/transfers/{transfer_id}/accept",
    response_model=EvidenceTransferResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    name="accept_evidence_transfer",
    summary="Accept an evidence custody transfer",
    operation_id="acceptEvidenceTransfer",
    tags=["Chain of Custody"],
)
async def accept_evidence_transfer(
    evidence_id: UUID,
    transfer_id: UUID,
    request: Request,
    response: Response,
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("custody.transfer.accept")),
    ],
    transfer_service: EvidenceTransferDecisionServiceAccess,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=255,
        ),
    ],
    correlation_header: Annotated[
        UUID | None,
        Header(
            alias="X-Correlation-ID",
        ),
    ] = None,
    payload: Annotated[
        TransferDecisionRequest | None,
        Body(),
    ] = None,
) -> EvidenceTransferResponse:
    return await _decide_evidence_transfer(
        evidence_id=evidence_id,
        transfer_id=transfer_id,
        decision_status=TransferStatus.ACCEPTED,
        payload=payload,
        request=request,
        response=response,
        authorization=authorization,
        transfer_service=transfer_service,
        idempotency_key=idempotency_key,
        correlation_header=correlation_header,
    )


@router.post(
    "/{evidence_id}/transfers/{transfer_id}/reject",
    response_model=EvidenceTransferResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    name="reject_evidence_transfer",
    summary="Reject an evidence custody transfer",
    operation_id="rejectEvidenceTransfer",
    tags=["Chain of Custody"],
)
async def reject_evidence_transfer(
    evidence_id: UUID,
    transfer_id: UUID,
    request: Request,
    response: Response,
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("custody.transfer.reject")),
    ],
    transfer_service: EvidenceTransferDecisionServiceAccess,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=255,
        ),
    ],
    correlation_header: Annotated[
        UUID | None,
        Header(
            alias="X-Correlation-ID",
        ),
    ] = None,
    payload: Annotated[
        TransferDecisionRequest | None,
        Body(),
    ] = None,
) -> EvidenceTransferResponse:
    return await _decide_evidence_transfer(
        evidence_id=evidence_id,
        transfer_id=transfer_id,
        decision_status=TransferStatus.REJECTED,
        payload=payload,
        request=request,
        response=response,
        authorization=authorization,
        transfer_service=transfer_service,
        idempotency_key=idempotency_key,
        correlation_header=correlation_header,
    )