from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
    TransferStatus,
)
from app.db.models.evidence import EvidenceTransfer
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import AuditRepository
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


class EvidenceTransferDecisionError(Exception):
    """Base transfer-decision domain error."""


class EvidenceTransferDecisionReferenceError(EvidenceTransferDecisionError):
    """Evidence or transfer does not exist."""


class EvidenceTransferDecisionActorError(EvidenceTransferDecisionError):
    """Actor is not the transfer recipient."""


class EvidenceTransferDecisionStateError(EvidenceTransferDecisionError):
    """Current transfer state prevents the decision."""


class EvidenceTransferDecisionIdempotencyConflictError(EvidenceTransferDecisionError):
    """Decision idempotency key conflicts with an earlier decision."""


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceTransferDecisionCommand:
    evidence_id: UUID
    transfer_id: UUID

    actor_user_id: UUID
    decision_status: TransferStatus

    idempotency_key: str
    correlation_id: str

    comment: str | None = None

    source_ip: str | None = None
    user_agent: str | None = None
    device_identifier: str | None = None

    def __post_init__(self) -> None:
        if self.decision_status not in {
            TransferStatus.ACCEPTED,
            TransferStatus.REJECTED,
        }:
            raise ValueError("decision_status must be ACCEPTED or REJECTED")

        if not (16 <= len(self.idempotency_key) <= 255):
            raise ValueError("idempotency_key must contain between 16 and 255 characters")

        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty")

        if self.comment is not None and len(self.comment) > 1000:
            raise ValueError("comment must not exceed 1000 characters")


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceTransferDecisionResult:
    transfer_id: UUID
    evidence_id: UUID

    from_user_id: UUID
    to_user_id: UUID

    purpose: str
    status: TransferStatus

    created_at: datetime
    decided_at: datetime

    decision_reason: str | None

    custody_record_id: UUID | None
    audit_log_id: UUID | None

    replayed: bool


class EvidenceTransferDecisionService:
    """Atomically accept or reject an evidence custody transfer."""

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

        self.audit = AuditRepository(session)

    async def decide(
        self,
        *,
        command: EvidenceTransferDecisionCommand,
    ) -> EvidenceTransferDecisionResult:
        try:
            evidence = await self.evidence.get_by_id_for_update(command.evidence_id)

            if evidence is None:
                raise (EvidenceTransferDecisionReferenceError("Evidence does not exist."))

            transfer = await self.transfers.get_by_id_for_update(
                transfer_id=(command.transfer_id),
                evidence_id=(command.evidence_id),
            )

            if transfer is None:
                raise (EvidenceTransferDecisionReferenceError("Evidence transfer does not exist."))

            # RBAC permission alone is not enough.
            # Only the named recipient may decide.
            if command.actor_user_id != transfer.to_user_id:
                raise EvidenceTransferDecisionActorError(
                    "Only the transfer recipient may accept or reject the transfer."
                )

            comment = self._normalize_comment(command.comment)

            if transfer.status is not TransferStatus.PENDING:
                if self._is_replay(
                    transfer=transfer,
                    command=command,
                    comment=comment,
                ):
                    result = self._result(
                        transfer=transfer,
                        custody_record_id=None,
                        audit_log_id=None,
                        replayed=True,
                    )

                    await self.session.rollback()

                    return result

                if transfer.decision_idempotency_key == command.idempotency_key:
                    raise (
                        EvidenceTransferDecisionIdempotencyConflictError(
                            "Decision idempotency key was already used for a different decision."
                        )
                    )

                raise EvidenceTransferDecisionStateError(
                    "Evidence transfer has already been decided."
                )

            now = datetime.now(UTC)

            if transfer.expires_at <= now:
                raise EvidenceTransferDecisionStateError("Evidence transfer has expired.")

            previous = await self.custody.get_latest_for_update(evidence_id=evidence.id)

            if previous is None:
                raise EvidenceTransferDecisionStateError("Evidence has no custody history.")

            event_type = self._event_type(command.decision_status)

            audit_action = self._audit_action(command.decision_status)

            metadata: dict[str, object] = {
                "correlation_id": (command.correlation_id),
                "transfer_id": str(transfer.id),
                "evidence_number": (evidence.evidence_number),
                "from_user_id": str(transfer.from_user_id),
                "to_user_id": str(transfer.to_user_id),
                "decision": (command.decision_status.value),
                "decision_reason": comment,
            }

            custody_integrity = build_custody_integrity(
                evidence_id=evidence.id,
                actor_user_id=(command.actor_user_id),
                from_user_id=(transfer.from_user_id),
                to_user_id=(transfer.to_user_id),
                previous_record_id=(previous.id),
                previous_record_hash=(previous.record_hash),
                transfer_id=transfer.id,
                event_type=event_type,
                purpose=transfer.purpose,
                source_ip=command.source_ip,
                device_identifier=(command.device_identifier),
                event_metadata=metadata,
                occurred_at=now,
            )

            custody_signature = self.signer.sign(custody_integrity.canonical_bytes)

            custody_record = await self.custody.create(
                evidence_id=evidence.id,
                actor_user_id=(command.actor_user_id),
                from_user_id=(transfer.from_user_id),
                to_user_id=(transfer.to_user_id),
                previous_record_id=(previous.id),
                transfer_id=transfer.id,
                event_type=event_type,
                purpose=transfer.purpose,
                source_ip=command.source_ip,
                device_identifier=(command.device_identifier),
                event_metadata=metadata,
                record_hash=(custody_integrity.record_hash),
                digital_signature=(custody_signature.to_json()),
                occurred_at=now,
            )

            await self.transfers.set_decision(
                transfer=transfer,
                status=(command.decision_status),
                decided_at=now,
                decision_reason=comment,
                decision_idempotency_key=(command.idempotency_key),
            )

            audit_log = await self.audit.create(
                actor_user_id=(command.actor_user_id),
                action=audit_action,
                resource_type="evidence",
                resource_id=evidence.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(command.correlation_id),
                occurred_at=now,
                source_ip=command.source_ip,
                user_agent=command.user_agent,
                details={
                    "transfer_id": str(transfer.id),
                    "evidence_id": str(evidence.id),
                    "from_user_id": str(transfer.from_user_id),
                    "to_user_id": str(transfer.to_user_id),
                    "decision": (command.decision_status.value),
                    "decision_reason": (comment),
                    "custody_record_id": str(custody_record.id),
                },
            )

            result = self._result(
                transfer=transfer,
                custody_record_id=(custody_record.id),
                audit_log_id=(audit_log.id),
                replayed=False,
            )

            await self.session.commit()

            return result

        except (
            EvidenceTransferDecisionReferenceError,
            EvidenceTransferDecisionActorError,
            EvidenceTransferDecisionStateError,
            EvidenceTransferDecisionIdempotencyConflictError,
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
        command: EvidenceTransferDecisionCommand,
        reason: str,
    ) -> None:
        occurred_at = datetime.now(UTC)

        await self.audit.create(
            actor_user_id=(command.actor_user_id),
            action=self._audit_action(command.decision_status),
            resource_type="evidence",
            resource_id=command.evidence_id,
            outcome=AuditOutcome.FAILURE,
            correlation_id=(command.correlation_id),
            occurred_at=occurred_at,
            source_ip=command.source_ip,
            user_agent=command.user_agent,
            details={
                "evidence_id": str(command.evidence_id),
                "transfer_id": str(command.transfer_id),
                "requested_decision": (command.decision_status.value),
                "reason": reason,
            },
        )

        await self.session.commit()

    @staticmethod
    def _normalize_comment(
        comment: str | None,
    ) -> str | None:
        if comment is None:
            return None

        normalized = comment.strip()

        return normalized or None

    @staticmethod
    def _is_replay(
        *,
        transfer: EvidenceTransfer,
        command: EvidenceTransferDecisionCommand,
        comment: str | None,
    ) -> bool:
        return (
            transfer.decision_idempotency_key == command.idempotency_key
            and transfer.status is command.decision_status
            and transfer.decision_reason == comment
        )

    @staticmethod
    def _event_type(
        decision_status: TransferStatus,
    ) -> CustodyEventType:
        if decision_status is TransferStatus.ACCEPTED:
            return CustodyEventType.TRANSFER_ACCEPTED

        if decision_status is TransferStatus.REJECTED:
            return CustodyEventType.TRANSFER_REJECTED

        raise ValueError("Unsupported transfer decision.")

    @staticmethod
    def _audit_action(
        decision_status: TransferStatus,
    ) -> AuditAction:
        if decision_status is TransferStatus.ACCEPTED:
            return AuditAction.CUSTODY_TRANSFER_ACCEPTED

        if decision_status is TransferStatus.REJECTED:
            return AuditAction.CUSTODY_TRANSFER_REJECTED

        raise ValueError("Unsupported transfer decision.")

    @staticmethod
    def _result(
        *,
        transfer: EvidenceTransfer,
        custody_record_id: UUID | None,
        audit_log_id: UUID | None,
        replayed: bool,
    ) -> EvidenceTransferDecisionResult:
        if transfer.decided_at is None:
            raise RuntimeError("Decided transfer has no decided_at.")

        return EvidenceTransferDecisionResult(
            transfer_id=transfer.id,
            evidence_id=transfer.evidence_id,
            from_user_id=transfer.from_user_id,
            to_user_id=transfer.to_user_id,
            purpose=transfer.purpose,
            status=transfer.status,
            created_at=transfer.created_at,
            decided_at=transfer.decided_at,
            decision_reason=(transfer.decision_reason),
            custody_record_id=(custody_record_id),
            audit_log_id=audit_log_id,
            replayed=replayed,
        )
