from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID, uuid4

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
    TransferStatus,
    VerificationStatus,
)
from app.modules.evidence.content_access import (
    EvidenceContentAccessCommand,
)
from app.modules.evidence.dependencies import (
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
    EvidenceVerificationNotFoundError,
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
    transfer_service: (EvidenceTransferDecisionServiceAccess),
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
                "code": ("EVIDENCE_TRANSFER_DECISION_NOT_FOUND"),
                "message": ("Evidence or evidence transfer was not found."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from None

    except EvidenceTransferDecisionActorError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": ("EVIDENCE_TRANSFER_DECISION_FORBIDDEN"),
                "message": ("Only the named transfer recipient may decide this transfer."),
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
                "code": ("EVIDENCE_TRANSFER_DECISION_CONFLICT"),
                "message": ("The evidence transfer cannot be decided in its current state."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from None

    response.headers["X-Correlation-ID"] = correlation_id

    return transfer_decision_response(result)


@router.get(
    "/{evidence_id}",
    name="get_evidence",
)
async def get_evidence(
    evidence_id: UUID,
    _: Annotated[
        AuthorizationContext,
        Depends(require_permission("evidence.read")),
    ],
) -> dict[str, str]:
    return {
        "evidenceId": str(evidence_id),
    }


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
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("evidence.content.read")),
    ],
    content_service: (EvidenceContentAccessServiceAccess),
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

    command = EvidenceContentAccessCommand(
        evidence_id=evidence_id,
        actor_user_id=authorization.user.id,
        correlation_id=correlation_id,
        source_ip=_source_ip(request),
        user_agent=_user_agent(request),
        device_identifier=None,
    )

    try:
        result = await content_service.retrieve(command=command)

    except EvidenceVerificationReferenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_NOT_FOUND",
                "message": ("The requested evidence was not found."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from exc

    except EvidenceRetrievalUnavailableError as exc:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": "EVIDENCE_UNAVAILABLE",
                "message": ("Evidence content is temporarily unavailable."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from exc

    except EvidenceRetrievalHashMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EVIDENCE_HASH_MISMATCH",
                "message": ("Evidence integrity verification failed."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from exc

    except EvidenceRetrievalSignatureInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": ("EVIDENCE_SIGNATURE_INVALID"),
                "message": ("Evidence authenticity verification failed."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from exc

    encoded_filename = quote(
        result.original_filename,
        safe="",
    )

    content_disposition = f"{disposition}; filename*=UTF-8''{encoded_filename}"

    return Response(
        content=result.content,
        media_type="application/octet-stream",
        headers={
            "X-Correlation-ID": correlation_id,
            "X-Evidence-SHA256": (result.original_sha256),
            "Content-Disposition": (content_disposition),
        },
    )


@router.post(
    "/{evidence_id}/verify",
    response_model=EvidenceVerificationResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    name="verify_evidence",
    summary=("Verify evidence integrity and authenticity"),
    operation_id="verifyEvidence",
)
async def verify_evidence(
    evidence_id: UUID,
    request: Request,
    response: Response,
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("evidence.verify")),
    ],
    verification_service: (EvidenceVerificationHTTPServiceAccess),
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

    command = EvidenceVerificationCommand(
        evidence_id=evidence_id,
        verified_by_user_id=(authorization.user.id),
        correlation_id=correlation_id,
        source_ip=_source_ip(request),
        user_agent=_user_agent(request),
        device_identifier=None,
        idempotency_key=idempotency_key,
    )

    try:
        outcome = await verification_service.verify(command=command)

    except EvidenceVerificationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_NOT_FOUND",
                "message": ("The requested evidence was not found."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        ) from exc

    verification = outcome.verification

    if verification.verification_status is VerificationStatus.HASH_MISMATCH:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": ("EVIDENCE_HASH_MISMATCH"),
                "message": ("Evidence integrity verification failed."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        )

    if verification.verification_status is VerificationStatus.SIGNATURE_INVALID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": ("EVIDENCE_SIGNATURE_INVALID"),
                "message": ("Evidence authenticity verification failed."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        )

    if verification.verification_status is VerificationStatus.UNAVAILABLE:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": "EVIDENCE_UNAVAILABLE",
                "message": ("Evidence verification is temporarily unavailable."),
            },
            headers={
                "X-Correlation-ID": correlation_id,
            },
        )

    response.headers["X-Correlation-ID"] = correlation_id

    return verification


@router.post(
    "/{evidence_id}/transfers",
    response_model=EvidenceTransferResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    name="initiate_evidence_transfer",
    summary=("Initiate an evidence custody transfer"),
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
    transfer_service: (EvidenceTransferInitiationServiceAccess),
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
                "code": ("EVIDENCE_TRANSFER_REFERENCE_NOT_FOUND"),
                "message": ("Evidence or transfer recipient was not found."),
            },
            headers={
                "X-Correlation-ID": (correlation_id),
            },
        ) from exc

    except (
        EvidenceTransferStateError,
        EvidenceTransferIdempotencyConflictError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": ("EVIDENCE_TRANSFER_CONFLICT"),
                "message": str(exc),
            },
            headers={
                "X-Correlation-ID": (correlation_id),
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
    summary=("Accept an evidence custody transfer"),
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
    transfer_service: (EvidenceTransferDecisionServiceAccess),
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
        decision_status=(TransferStatus.ACCEPTED),
        payload=payload,
        request=request,
        response=response,
        authorization=authorization,
        transfer_service=transfer_service,
        idempotency_key=idempotency_key,
        correlation_header=(correlation_header),
    )


@router.post(
    "/{evidence_id}/transfers/{transfer_id}/reject",
    response_model=EvidenceTransferResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    name="reject_evidence_transfer",
    summary=("Reject an evidence custody transfer"),
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
    transfer_service: (EvidenceTransferDecisionServiceAccess),
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
        decision_status=(TransferStatus.REJECTED),
        payload=payload,
        request=request,
        response=response,
        authorization=authorization,
        transfer_service=transfer_service,
        idempotency_key=idempotency_key,
        correlation_header=(correlation_header),
    )
