from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
    EvidenceStatus,
)
from app.db.models.evidence import (
    CustodyRecord,
    Evidence,
)
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import (
    AuditRepository,
)
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

_IDEMPOTENCY_SCOPE = "EVIDENCE_QUARANTINE"

_QUARANTINABLE_STATUSES = frozenset(
    {
        EvidenceStatus.STORED,
        EvidenceStatus.VERIFIED,
        EvidenceStatus.COMPROMISED,
    }
)


class EvidenceQuarantineError(Exception):
    """Base evidence-quarantine domain error."""


class EvidenceQuarantineReferenceError(EvidenceQuarantineError):
    """Evidence does not exist."""


class EvidenceQuarantineStateError(EvidenceQuarantineError):
    """Evidence cannot be quarantined in its current state."""


class EvidenceQuarantineIdempotencyConflictError(EvidenceQuarantineError):
    """Idempotency key conflicts with another request."""


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceQuarantineCommand:
    evidence_id: UUID
    actor_user_id: UUID

    reason: str

    idempotency_key: str
    correlation_id: str

    source_ip: str | None = None
    user_agent: str | None = None
    device_identifier: str | None = None

    def __post_init__(self) -> None:
        reason = self.reason.strip()

        if not (5 <= len(reason) <= 2000):
            raise ValueError("reason must contain between 5 and 2000 characters")

        if not (16 <= len(self.idempotency_key) <= 255):
            raise ValueError("idempotency_key must contain between 16 and 255 characters")

        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty")


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceQuarantineResult:
    evidence_id: UUID
    evidence_number: str

    status: EvidenceStatus
    reason: str

    quarantined_at: datetime

    custody_record_id: UUID | None
    audit_log_id: UUID | None

    replayed: bool


class EvidenceQuarantineService:
    """Atomically quarantine persisted forensic evidence."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        signer: ForensicSigner,
    ) -> None:
        self.session = session
        self.signer = signer

        self.evidence = EvidenceRepository(session)

        self.custody = CustodyRepository(session)

        self.audit = AuditRepository(session)

    async def quarantine(
        self,
        *,
        command: EvidenceQuarantineCommand,
    ) -> EvidenceQuarantineResult:
        try:
            evidence = await self.evidence.get_by_id_for_update(command.evidence_id)

            if evidence is None:
                raise (EvidenceQuarantineReferenceError("Evidence does not exist."))

            reason = command.reason.strip()

            existing = await self.custody.get_by_idempotency(
                evidence_id=evidence.id,
                idempotency_scope=(_IDEMPOTENCY_SCOPE),
                idempotency_key=(command.idempotency_key),
            )

            if existing is not None:
                result = self._resolve_replay(
                    evidence=evidence,
                    existing=existing,
                    command=command,
                    reason=reason,
                )

                await self.session.rollback()

                return result

            if evidence.status is EvidenceStatus.QUARANTINED:
                raise EvidenceQuarantineStateError("Evidence is already quarantined.")

            if evidence.status not in _QUARANTINABLE_STATUSES:
                raise EvidenceQuarantineStateError(
                    f"Evidence cannot be quarantined from status {evidence.status.value}."
                )

            previous = await self.custody.get_latest_for_update(evidence_id=evidence.id)

            if previous is None:
                raise EvidenceQuarantineStateError("Evidence has no custody history.")

            now = datetime.now(UTC)

            previous_status = evidence.status

            metadata: dict[str, object] = {
                "correlation_id": (command.correlation_id),
                "evidence_number": (evidence.evidence_number),
                "previous_status": (previous_status.value),
                "new_status": (EvidenceStatus.QUARANTINED.value),
                "reason": reason,
                "idempotency_scope": (_IDEMPOTENCY_SCOPE),
            }

            integrity = build_custody_integrity(
                evidence_id=evidence.id,
                actor_user_id=(command.actor_user_id),
                from_user_id=None,
                to_user_id=None,
                previous_record_id=(previous.id),
                previous_record_hash=(previous.record_hash),
                transfer_id=None,
                event_type=(CustodyEventType.QUARANTINED),
                purpose=reason,
                source_ip=command.source_ip,
                device_identifier=(command.device_identifier),
                event_metadata=metadata,
                occurred_at=now,
            )

            signature = self.signer.sign(integrity.canonical_bytes)

            custody_record = await self.custody.create(
                evidence_id=evidence.id,
                actor_user_id=(command.actor_user_id),
                from_user_id=None,
                to_user_id=None,
                previous_record_id=(previous.id),
                transfer_id=None,
                event_type=(CustodyEventType.QUARANTINED),
                purpose=reason,
                source_ip=(command.source_ip),
                device_identifier=(command.device_identifier),
                event_metadata=metadata,
                record_hash=(integrity.record_hash),
                digital_signature=(signature.to_json()),
                occurred_at=now,
                idempotency_scope=(_IDEMPOTENCY_SCOPE),
                idempotency_key=(command.idempotency_key),
            )

            await self.evidence.set_status(
                evidence=evidence,
                status=(EvidenceStatus.QUARANTINED),
            )

            audit_log = await self.audit.create(
                actor_user_id=(command.actor_user_id),
                action=(AuditAction.EVIDENCE_QUARANTINED),
                resource_type="evidence",
                resource_id=evidence.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(command.correlation_id),
                occurred_at=now,
                source_ip=command.source_ip,
                user_agent=command.user_agent,
                details={
                    "evidence_id": str(evidence.id),
                    "evidence_number": (evidence.evidence_number),
                    "previous_status": (previous_status.value),
                    "new_status": (EvidenceStatus.QUARANTINED.value),
                    "reason": reason,
                    "custody_record_id": str(custody_record.id),
                    "idempotency_scope": (_IDEMPOTENCY_SCOPE),
                },
            )

            result = EvidenceQuarantineResult(
                evidence_id=evidence.id,
                evidence_number=(evidence.evidence_number),
                status=(EvidenceStatus.QUARANTINED),
                reason=reason,
                quarantined_at=now,
                custody_record_id=(custody_record.id),
                audit_log_id=(audit_log.id),
                replayed=False,
            )

            await self.session.commit()

            return result

        except (
            EvidenceQuarantineReferenceError,
            EvidenceQuarantineStateError,
            EvidenceQuarantineIdempotencyConflictError,
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

    def _resolve_replay(
        self,
        *,
        evidence: Evidence,
        existing: CustodyRecord,
        command: EvidenceQuarantineCommand,
        reason: str,
    ) -> EvidenceQuarantineResult:
        identical = (
            existing.event_type is CustodyEventType.QUARANTINED
            and existing.actor_user_id == command.actor_user_id
            and existing.purpose == reason
        )

        if not identical:
            raise (
                EvidenceQuarantineIdempotencyConflictError(
                    "Idempotency key was already used for a different quarantine request."
                )
            )

        if evidence.status is not EvidenceStatus.QUARANTINED:
            raise EvidenceQuarantineStateError(
                "Quarantine custody record exists but evidence status is inconsistent."
            )

        return EvidenceQuarantineResult(
            evidence_id=evidence.id,
            evidence_number=(evidence.evidence_number),
            status=evidence.status,
            reason=reason,
            quarantined_at=(existing.occurred_at),
            custody_record_id=None,
            audit_log_id=None,
            replayed=True,
        )

    async def _record_failure(
        self,
        *,
        command: EvidenceQuarantineCommand,
        reason: str,
    ) -> None:
        occurred_at = datetime.now(UTC)

        await self.audit.create(
            actor_user_id=(command.actor_user_id),
            action=(AuditAction.EVIDENCE_QUARANTINED),
            resource_type="evidence",
            resource_id=command.evidence_id,
            outcome=AuditOutcome.FAILURE,
            correlation_id=(command.correlation_id),
            occurred_at=occurred_at,
            source_ip=command.source_ip,
            user_agent=command.user_agent,
            details={
                "evidence_id": str(command.evidence_id),
                "requested_reason": (command.reason.strip()),
                "idempotency_scope": (_IDEMPOTENCY_SCOPE),
                "reason": reason,
            },
        )

        await self.session.commit()
