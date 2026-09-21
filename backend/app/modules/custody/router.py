from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from app.db.models.evidence import CustodyRecord
from app.modules.custody.dependencies import CustodyServiceAccess
from app.modules.custody.errors import (
    CustodyEvidenceNotFoundError,
    CustodyIdempotencyConflictError,
)
from app.modules.custody.schema import (
    CreateCustodyEventRequest,
    CustodyEventPageResponse,
    CustodyEventResponse,
    PaginationMeta,
)
from app.modules.custody.service import (
    AppendCustodyEventCommand,
    ListCustodyEventsCommand,
)
from app.modules.rbac.dependencies import (
    AuthorizationContext,
    require_permission,
)

router = APIRouter(tags=["Chain of Custody"])


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


def _source_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    host = request.client.host
    return host[:64] if host else None


def _user_agent(request: Request) -> str | None:
    value = request.headers.get("User-Agent")
    if value is None:
        return None
    return value[:4096]


def _to_response(record: CustodyRecord,) -> CustodyEventResponse:
    return CustodyEventResponse(
        id=record.id,
        evidence_id=record.evidence_id,
        actor_user_id=record.actor_user_id,
        from_user_id=record.from_user_id,
        to_user_id=record.to_user_id,
        previous_record_id=record.previous_record_id,
        event_type=record.event_type,
        purpose=record.purpose,
        source_ip=str(record.source_ip) if record.source_ip is not None else None,
        device_identifier=record.device_identifier,
        event_metadata=dict(record.event_metadata) if record.event_metadata else {},
        record_hash=record.record_hash,
        digital_signature=record.digital_signature,
        occurred_at=record.occurred_at,
    )


@router.get(
    "/evidence/{evidence_id}/custody-events",
    response_model=CustodyEventPageResponse,
    response_model_by_alias=True,
)
async def list_custody_events(
    evidence_id: UUID,
    request: Request,
    response: Response,
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("custody.read")),
    ],
    custody_service: CustodyServiceAccess,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    correlation_id_header: Annotated[
        UUID | None,
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> CustodyEventPageResponse:
    correlation_id = _correlation_id(
        request,
        header_value=correlation_id_header,
    )

    command = ListCustodyEventsCommand(
        evidence_id=evidence_id,
        actor_user_id=authorization.user.id,
        correlation_id=correlation_id,
        page=page,
        page_size=page_size,
        source_ip=_source_ip(request),
        user_agent=_user_agent(request),
    )

    try:
        result = await custody_service.list_events(command=command)
    except CustodyEvidenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_NOT_FOUND",
                "message": str(exc),
            },
            headers={"X-Correlation-ID": correlation_id},
        ) from exc

    response.headers["X-Correlation-ID"] = correlation_id

    total_pages = (
        (result.total + page_size - 1) // page_size
        if page_size > 0
        else 0
    )
    
    return CustodyEventPageResponse(
        items=[_to_response(r) for r in result.items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=result.total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@router.post(
    "/evidence/{evidence_id}/custody-events",
    response_model=CustodyEventResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_custody_event(
    evidence_id: UUID,
    payload: CreateCustodyEventRequest,
    request: Request,
    response: Response,
    authorization: Annotated[
        AuthorizationContext,
        Depends(require_permission("custody.create")),
    ],
    custody_service: CustodyServiceAccess,
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
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> CustodyEventResponse:
    correlation_id = _correlation_id(
        request,
        header_value=correlation_id_header,
    )

    command = AppendCustodyEventCommand(
        evidence_id=evidence_id,
        actor_user_id=authorization.user.id,
        event_type=payload.event_type,
        purpose=payload.purpose,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        source_ip=_source_ip(request),
        user_agent=_user_agent(request),
        device_identifier=None,
        event_metadata=payload.event_metadata,
    )

    try:
        result = await custody_service.append_event(command=command)
    except CustodyEvidenceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_NOT_FOUND",
                "message": str(exc),
            },
            headers={"X-Correlation-ID": correlation_id},
        ) from exc
    except CustodyIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CUSTODY_IDEMPOTENCY_CONFLICT",
                "message": str(exc),
            },
            headers={"X-Correlation-ID": correlation_id},
        ) from exc

    response.headers["X-Correlation-ID"] = correlation_id

    return _to_response(result.custody_record)
