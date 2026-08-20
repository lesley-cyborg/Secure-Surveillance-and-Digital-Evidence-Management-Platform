from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    CustodyEventType,
)
from app.db.models.evidence import (
    CustodyRecord,
)


class CustodyRepository:
    """Append-only chain-of-custody persistence."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def get_latest_for_update(
        self,
        *,
        evidence_id: UUID,
    ) -> CustodyRecord | None:
        statement = (
            select(CustodyRecord)
            .where(CustodyRecord.evidence_id == evidence_id)
            .order_by(
                CustodyRecord.occurred_at.desc(),
                CustodyRecord.created_at.desc(),
                CustodyRecord.id.desc(),
            )
            .limit(1)
            .with_for_update()
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        evidence_id: UUID,
        idempotency_scope: str | None = None,
        idempotency_key: str | None = None,
        actor_user_id: UUID | None,
        from_user_id: UUID | None,
        to_user_id: UUID | None,
        previous_record_id: UUID | None,
        transfer_id: UUID | None,
        event_type: CustodyEventType,
        purpose: str | None,
        source_ip: str | None,
        device_identifier: str | None,
        event_metadata: dict[str, object],
        record_hash: str,
        digital_signature: str,
        occurred_at: datetime,
    ) -> CustodyRecord:
        record = CustodyRecord(
            evidence_id=evidence_id,
            idempotency_scope=idempotency_scope,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            previous_record_id=(previous_record_id),
            transfer_id=transfer_id,
            event_type=event_type,
            purpose=purpose,
            source_ip=source_ip,
            device_identifier=(device_identifier),
            event_metadata=event_metadata,
            record_hash=record_hash,
            digital_signature=(digital_signature),
            occurred_at=occurred_at,
        )

        self.session.add(record)
        await self.session.flush()

        return record

    async def get_custodian_anchor_for_update(
        self,
        *,
        evidence_id: UUID,
    ) -> CustodyRecord | None:
        statement = (
            select(CustodyRecord)
            .where(
                CustodyRecord.evidence_id == evidence_id,
                CustodyRecord.event_type.in_(
                    (
                        CustodyEventType.ACQUIRED,
                        CustodyEventType.TRANSFER_ACCEPTED,
                    )
                ),
            )
            .order_by(
                CustodyRecord.occurred_at.desc(),
                CustodyRecord.created_at.desc(),
                CustodyRecord.id.desc(),
            )
            .limit(1)
            .with_for_update()
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_idempotency(
        self,
        *,
        evidence_id: UUID,
        idempotency_scope: str,
        idempotency_key: str,
    ) -> CustodyRecord | None:
        statement = select(CustodyRecord).where(
            CustodyRecord.evidence_id == evidence_id,
            CustodyRecord.idempotency_scope == idempotency_scope,
            CustodyRecord.idempotency_key == idempotency_key,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()
