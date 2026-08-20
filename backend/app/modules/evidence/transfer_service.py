from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
    EvidenceStatus,
    TransferStatus,
)
from app.db.models.evidence import EvidenceTransfer
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import AuditRepository
from app.modules.auth.repository import UserRepository
from app.modules.custody.integrity import (
    build_custody_integrity,
)
from app.modules.custody.repository import (
    CustodyRepository,
)
from app.modules.evidence.repository import (
    EvidenceRepository,
)
from app.modules.evidence.signing import (
    ForensicSigner,
)
from app.modules.evidence.transfer_repository import (
    EvidenceTransferRepository,
)


class EvidenceTransferError(Exception):
    """Base evidence-transfer domain error."""


class EvidenceTransferReferenceError(EvidenceTransferError):
    """Evidence or recipient reference is invalid."""


class EvidenceTransferStateError(EvidenceTransferError):
    """Evidence custody state prevents transfer."""


class EvidenceTransferIdempotencyConflictError(EvidenceTransferError):
    """An idempotency key was reused with another request."""


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceTransferInitiationCommand:
    evidence_id: UUID

    to_user_id: UUID
    initiated_by_user_id: UUID

    purpose: str
    expires_at: datetime

    idempotency_key: str

    correlation_id: str

    source_ip: str | None = None
    user_agent: str | None = None
    device_identifier: str | None = None

    def __post_init__(self) -> None:
        purpose = self.purpose.strip()

        if not 5 <= len(purpose) <= 1000:
            raise ValueError("purpose must contain between 5 and 1000 characters")

        if not (16 <= len(self.idempotency_key) <= 255):
            raise ValueError("idempotency_key must contain between 16 and 255 characters")

        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty")

        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceTransferInitiationResult:
    transfer_id: UUID

    evidence_id: UUID

    from_user_id: UUID
    to_user_id: UUID
    initiated_by_user_id: UUID

    purpose: str
    status: TransferStatus

    expires_at: datetime
    created_at: datetime

    custody_record_id: UUID | None
    audit_log_id: UUID | None

    replayed: bool


_TRANSFERABLE_STATUSES = frozenset(
    {
        EvidenceStatus.STORED,
        EvidenceStatus.VERIFIED,
    }
)


class EvidenceTransferInitiationService:
    """Create one atomic custody-transfer initiation."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        signer: ForensicSigner,
    ) -> None:
        self.session = session
        self.signer = signer

        self.evidence = EvidenceRepository(session)

        self.transfers = EvidenceTransferRepository(session)

        self.custody = CustodyRepository(session)

        self.users = UserRepository(session)

        self.audit = AuditRepository(session)

    async def initiate(
        self,
        *,
        command: EvidenceTransferInitiationCommand,
    ) -> EvidenceTransferInitiationResult:
        now = datetime.now(UTC)

        if command.expires_at <= now:
            raise ValueError("expires_at must be in the future")

        try:
            evidence = await self.evidence.get_by_id_for_update(command.evidence_id)

            if evidence is None:
                raise EvidenceTransferReferenceError("Evidence does not exist.")

            existing = await self.transfers.get_by_idempotency_key(
                evidence_id=evidence.id,
                idempotency_key=(command.idempotency_key),
            )

            if existing is not None:
                self._validate_replay(
                    transfer=existing,
                    command=command,
                )

                result = self._result(
                    transfer=existing,
                    custody_record_id=None,
                    audit_log_id=None,
                    replayed=True,
                )

                await self.session.rollback()

                return result

            if evidence.status not in _TRANSFERABLE_STATUSES:
                raise EvidenceTransferStateError(
                    "Evidence status does not permit custody transfer."
                )

            recipient = await self.users.get_by_id(command.to_user_id)

            if recipient is None or not recipient.is_active:
                raise EvidenceTransferReferenceError(
                    "Transfer recipient does not exist or is inactive."
                )

            custody_anchor = await self.custody.get_custodian_anchor_for_update(
                evidence_id=evidence.id
            )

            if custody_anchor is None:
                raise EvidenceTransferStateError("Evidence has no established human custodian.")

            current_custodian_id = self._resolve_custodian(custody_anchor)

            if current_custodian_id is None:
                raise EvidenceTransferStateError("Evidence has no established human custodian.")

            if current_custodian_id == command.to_user_id:
                raise EvidenceTransferStateError(
                    "Transfer recipient is already the current custodian."
                )

            pending = await self.transfers.get_pending_for_evidence_for_update(
                evidence_id=evidence.id
            )

            if pending is not None:
                raise EvidenceTransferStateError("Evidence already has a pending custody transfer.")

            transfer = await self.transfers.create(
                evidence_id=evidence.id,
                from_user_id=(current_custodian_id),
                to_user_id=(command.to_user_id),
                initiated_by_user_id=(command.initiated_by_user_id),
                idempotency_key=(command.idempotency_key),
                purpose=(command.purpose.strip()),
                expires_at=(command.expires_at),
            )

            previous = await self.custody.get_latest_for_update(evidence_id=evidence.id)

            if previous is None:
                raise EvidenceTransferStateError("Evidence has no custody history.")

            occurred_at = datetime.now(UTC)

            metadata: dict[str, object] = {
                "correlation_id": (command.correlation_id),
                "transfer_id": str(transfer.id),
                "evidence_number": (evidence.evidence_number),
                "from_user_id": str(current_custodian_id),
                "to_user_id": str(command.to_user_id),
                "initiated_by_user_id": str(command.initiated_by_user_id),
                "expires_at": (command.expires_at.astimezone(UTC).isoformat()),
            }

            custody_integrity = build_custody_integrity(
                evidence_id=evidence.id,
                actor_user_id=(command.initiated_by_user_id),
                from_user_id=(current_custodian_id),
                to_user_id=(command.to_user_id),
                previous_record_id=(previous.id),
                previous_record_hash=(previous.record_hash),
                transfer_id=transfer.id,
                event_type=(CustodyEventType.TRANSFER_INITIATED),
                purpose=(command.purpose.strip()),
                source_ip=(command.source_ip),
                device_identifier=(command.device_identifier),
                event_metadata=metadata,
                occurred_at=occurred_at,
            )

            custody_signature = self.signer.sign(custody_integrity.canonical_bytes)

            custody_record = await self.custody.create(
                evidence_id=evidence.id,
                actor_user_id=(command.initiated_by_user_id),
                from_user_id=(current_custodian_id),
                to_user_id=(command.to_user_id),
                previous_record_id=(previous.id),
                transfer_id=transfer.id,
                event_type=(CustodyEventType.TRANSFER_INITIATED),
                purpose=(command.purpose.strip()),
                source_ip=(command.source_ip),
                device_identifier=(command.device_identifier),
                event_metadata=metadata,
                record_hash=(custody_integrity.record_hash),
                digital_signature=(custody_signature.to_json()),
                occurred_at=occurred_at,
            )

            audit_log = await self.audit.create(
                actor_user_id=(command.initiated_by_user_id),
                action=(AuditAction.CUSTODY_TRANSFER_INITIATED),
                resource_type=("evidence"),
                resource_id=evidence.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(command.correlation_id),
                occurred_at=occurred_at,
                source_ip=command.source_ip,
                user_agent=command.user_agent,
                details={
                    "transfer_id": str(transfer.id),
                    "evidence_id": str(evidence.id),
                    "evidence_number": (evidence.evidence_number),
                    "from_user_id": str(current_custodian_id),
                    "to_user_id": str(command.to_user_id),
                    "expires_at": (command.expires_at.astimezone(UTC).isoformat()),
                    "custody_record_id": str(custody_record.id),
                },
            )

            result = self._result(
                transfer=transfer,
                custody_record_id=(custody_record.id),
                audit_log_id=audit_log.id,
                replayed=False,
            )

            await self.session.commit()

            return result

        except (
            EvidenceTransferReferenceError,
            EvidenceTransferStateError,
            EvidenceTransferIdempotencyConflictError,
        ) as exc:
            await self.session.rollback()

            await self._record_failure(
                command=command,
                reason=type(exc).__name__,
            )

            raise

        except Exception:
            await self.session.rollback()
            raise

    async def _record_failure(
        self,
        *,
        command: EvidenceTransferInitiationCommand,
        reason: str,
    ) -> None:
        occurred_at = datetime.now(UTC)

        await self.audit.create(
            actor_user_id=(command.initiated_by_user_id),
            action=(AuditAction.CUSTODY_TRANSFER_INITIATED),
            resource_type="evidence",
            resource_id=command.evidence_id,
            outcome=AuditOutcome.FAILURE,
            correlation_id=(command.correlation_id),
            occurred_at=occurred_at,
            source_ip=command.source_ip,
            user_agent=command.user_agent,
            details={
                "evidence_id": str(command.evidence_id),
                "to_user_id": str(command.to_user_id),
                "idempotency_key": (command.idempotency_key),
                "reason": reason,
            },
        )

        await self.session.commit()

    @staticmethod
    def _resolve_custodian(
        custody_record: object,
    ) -> UUID | None:
        event_type = getattr(
            custody_record,
            "event_type",
            None,
        )

        if event_type is CustodyEventType.TRANSFER_ACCEPTED:
            return getattr(
                custody_record,
                "to_user_id",
                None,
            )

        if event_type is CustodyEventType.ACQUIRED:
            return getattr(
                custody_record,
                "actor_user_id",
                None,
            )

        return None

    @staticmethod
    def _validate_replay(
        *,
        transfer: EvidenceTransfer,
        command: EvidenceTransferInitiationCommand,
    ) -> None:
        same_request = (
            transfer.to_user_id == command.to_user_id
            and transfer.initiated_by_user_id == command.initiated_by_user_id
            and transfer.purpose == command.purpose.strip()
            and transfer.expires_at == command.expires_at
        )

        if not same_request:
            raise (
                EvidenceTransferIdempotencyConflictError(
                    "Idempotency key was already used for another transfer request."
                )
            )

    @staticmethod
    def _result(
        *,
        transfer: EvidenceTransfer,
        custody_record_id: UUID | None,
        audit_log_id: UUID | None,
        replayed: bool,
    ) -> EvidenceTransferInitiationResult:
        return EvidenceTransferInitiationResult(
            transfer_id=transfer.id,
            evidence_id=(transfer.evidence_id),
            from_user_id=(transfer.from_user_id),
            to_user_id=(transfer.to_user_id),
            initiated_by_user_id=(transfer.initiated_by_user_id),
            purpose=transfer.purpose,
            status=transfer.status,
            expires_at=(transfer.expires_at),
            created_at=(transfer.created_at),
            custody_record_id=(custody_record_id),
            audit_log_id=audit_log_id,
            replayed=replayed,
        )
