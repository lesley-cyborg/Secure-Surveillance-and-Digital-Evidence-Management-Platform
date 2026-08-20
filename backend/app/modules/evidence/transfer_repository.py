from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import TransferStatus
from app.db.models.evidence import EvidenceTransfer


class EvidenceTransferRepository:
    """Persistence for evidence custody-transfer workflow state.

    Methods flush but never commit. Transaction boundaries belong
    to the lifecycle service.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def create(
        self,
        *,
        evidence_id: UUID,
        from_user_id: UUID,
        to_user_id: UUID,
        initiated_by_user_id: UUID,
        idempotency_key: str,
        purpose: str,
        expires_at: datetime,
    ) -> EvidenceTransfer:
        transfer = EvidenceTransfer(
            evidence_id=evidence_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            initiated_by_user_id=(initiated_by_user_id),
            idempotency_key=idempotency_key,
            purpose=purpose,
            status=TransferStatus.PENDING,
            expires_at=expires_at,
            decided_at=None,
            decision_reason=None,
        )

        self.session.add(transfer)
        await self.session.flush()

        return transfer

    async def get_by_id(
        self,
        transfer_id: UUID,
    ) -> EvidenceTransfer | None:
        return await self.session.get(
            EvidenceTransfer,
            transfer_id,
        )

    async def get_by_id_for_update(
        self,
        *,
        transfer_id: UUID,
        evidence_id: UUID,
    ) -> EvidenceTransfer | None:
        statement = (
            select(EvidenceTransfer)
            .where(
                EvidenceTransfer.id == transfer_id,
                EvidenceTransfer.evidence_id == evidence_id,
            )
            .with_for_update()
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self,
        *,
        evidence_id: UUID,
        idempotency_key: str,
    ) -> EvidenceTransfer | None:
        statement = select(EvidenceTransfer).where(
            EvidenceTransfer.evidence_id == evidence_id,
            EvidenceTransfer.idempotency_key == idempotency_key,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_pending_for_evidence(
        self,
        *,
        evidence_id: UUID,
    ) -> EvidenceTransfer | None:
        statement = select(EvidenceTransfer).where(
            EvidenceTransfer.evidence_id == evidence_id,
            EvidenceTransfer.status == TransferStatus.PENDING,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_pending_for_evidence_for_update(
        self,
        *,
        evidence_id: UUID,
    ) -> EvidenceTransfer | None:
        statement = (
            select(EvidenceTransfer)
            .where(
                EvidenceTransfer.evidence_id == evidence_id,
                EvidenceTransfer.status == TransferStatus.PENDING,
            )
            .with_for_update()
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def set_decision(
        self,
        *,
        transfer: EvidenceTransfer,
        status: TransferStatus,
        decided_at: datetime,
        decision_reason: str | None,
        decision_idempotency_key: str,
    ) -> None:
        if status not in {
            TransferStatus.ACCEPTED,
            TransferStatus.REJECTED,
        }:
            raise ValueError("Transfer decision status must be ACCEPTED or REJECTED.")

        transfer.status = status
        transfer.decided_at = decided_at
        transfer.decision_reason = decision_reason
        transfer.decision_idempotency_key = decision_idempotency_key

        await self.session.flush()
