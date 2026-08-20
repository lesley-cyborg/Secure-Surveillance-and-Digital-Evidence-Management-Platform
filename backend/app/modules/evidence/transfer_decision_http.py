from __future__ import annotations

from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.db.models.enums import TransferStatus
from app.modules.evidence.transfer_decision_service import (
    EvidenceTransferDecisionCommand,
    EvidenceTransferDecisionResult,
)
from app.modules.evidence.transfer_http import (
    EvidenceTransferResponse,
)


class TransferDecisionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    comment: str | None = Field(
        default=None,
        max_length=1000,
    )


def build_transfer_decision_command(
    *,
    evidence_id: UUID,
    transfer_id: UUID,
    actor_user_id: UUID,
    decision_status: TransferStatus,
    idempotency_key: str,
    correlation_id: str,
    comment: str | None,
    source_ip: str | None,
    user_agent: str | None,
    device_identifier: str | None,
) -> EvidenceTransferDecisionCommand:
    return EvidenceTransferDecisionCommand(
        evidence_id=evidence_id,
        transfer_id=transfer_id,
        actor_user_id=actor_user_id,
        decision_status=decision_status,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        comment=comment,
        source_ip=source_ip,
        user_agent=user_agent,
        device_identifier=device_identifier,
    )


def transfer_decision_response(
    result: EvidenceTransferDecisionResult,
) -> EvidenceTransferResponse:
    return EvidenceTransferResponse(
        id=result.transfer_id,
        evidence_id=result.evidence_id,
        from_user_id=result.from_user_id,
        to_user_id=result.to_user_id,
        purpose=result.purpose,
        status=result.status,
        created_at=result.created_at,
        decided_at=result.decided_at,
    )
