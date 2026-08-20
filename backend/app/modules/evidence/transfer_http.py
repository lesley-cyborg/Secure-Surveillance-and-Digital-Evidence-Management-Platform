from __future__ import annotations

from datetime import (
    UTC,
    datetime,
    timedelta,
)
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from pydantic.alias_generators import to_camel

from app.db.models.enums import (
    TransferStatus,
)
from app.modules.evidence.transfer_service import (
    EvidenceTransferInitiationCommand,
    EvidenceTransferInitiationResult,
)

# The OpenAPI contract allows expiresAt to
# be omitted/null but does not define the
# default lifetime. This is an application
# policy, not an OpenAPI requirement.
_DEFAULT_TRANSFER_TTL = timedelta(hours=24)


class EvidenceTransferRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    to_user_id: UUID

    purpose: str = Field(
        min_length=5,
        max_length=1000,
    )

    expires_at: datetime | None = None


class EvidenceTransferResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    id: UUID
    evidence_id: UUID
    from_user_id: UUID
    to_user_id: UUID

    purpose: str
    status: TransferStatus

    created_at: datetime
    decided_at: datetime | None = None


def resolve_transfer_expiry(
    expires_at: datetime | None,
) -> datetime:
    if expires_at is None:
        return datetime.now(UTC) + _DEFAULT_TRANSFER_TTL

    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("expiresAt must include a timezone")

    return expires_at


def build_transfer_command(
    *,
    evidence_id: UUID,
    actor_user_id: UUID,
    request: EvidenceTransferRequest,
    idempotency_key: str,
    correlation_id: str,
    source_ip: str | None,
    user_agent: str | None,
) -> EvidenceTransferInitiationCommand:
    return EvidenceTransferInitiationCommand(
        evidence_id=evidence_id,
        to_user_id=request.to_user_id,
        initiated_by_user_id=(actor_user_id),
        purpose=request.purpose,
        expires_at=resolve_transfer_expiry(request.expires_at),
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        source_ip=source_ip,
        user_agent=user_agent,
        device_identifier=None,
    )


def transfer_response(
    result: EvidenceTransferInitiationResult,
) -> EvidenceTransferResponse:
    return EvidenceTransferResponse(
        id=result.transfer_id,
        evidence_id=result.evidence_id,
        from_user_id=result.from_user_id,
        to_user_id=result.to_user_id,
        purpose=result.purpose,
        status=result.status,
        created_at=result.created_at,
        decided_at=None,
    )
