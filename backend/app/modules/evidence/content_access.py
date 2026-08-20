from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
)
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import AuditRepository
from app.modules.custody.integrity import (
    build_custody_integrity,
)
from app.modules.custody.repository import (
    CustodyRepository,
)
from app.modules.evidence.errors import (
    EvidenceRetrievalHashMismatchError,
    EvidenceRetrievalSignatureInvalidError,
    EvidenceRetrievalUnavailableError,
    EvidenceVerificationReferenceError,
)
from app.modules.evidence.repository import (
    EvidenceRepository,
)
from app.modules.evidence.signing import (
    ForensicSigner,
)
from app.modules.evidence.verification import (
    EvidenceRetrievalResult,
    EvidenceVerificationCommand,
)
from app.modules.evidence.verification_orchestrator import (
    EvidenceVerificationOrchestrator,
)


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceContentAccessCommand:
    evidence_id: UUID
    actor_user_id: UUID

    correlation_id: str

    source_ip: str | None = None
    user_agent: str | None = None
    device_identifier: str | None = None

    def __post_init__(self) -> None:
        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty")


class EvidenceContentAccessService:
    """
    Perform controlled plaintext evidence retrieval.

    Plaintext is returned only after:

    1. forensic verification succeeds;
    2. a VIEWED custody record is appended;
    3. EVIDENCE_CONTENT_VIEWED audit succeeds; and
    4. the custody/audit transaction commits.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        orchestrator: EvidenceVerificationOrchestrator,
        signer: ForensicSigner,
    ) -> None:
        self.session = session
        self.orchestrator = orchestrator
        self.signer = signer

        self.evidence = EvidenceRepository(session)
        self.custody = CustodyRepository(session)
        self.audit = AuditRepository(session)

    async def retrieve(
        self,
        *,
        command: EvidenceContentAccessCommand,
    ) -> EvidenceRetrievalResult:
        verification_command = EvidenceVerificationCommand(
            evidence_id=command.evidence_id,
            verified_by_user_id=(command.actor_user_id),
            correlation_id=(command.correlation_id),
            source_ip=command.source_ip,
            user_agent=command.user_agent,
            device_identifier=(command.device_identifier),
            idempotency_key=None,
        )

        try:
            retrieval = await self.orchestrator.retrieve(command=verification_command)

        except EvidenceVerificationReferenceError:
            await self._record_failure(
                command=command,
                reason="evidence_not_found",
            )
            raise

        except EvidenceRetrievalUnavailableError:
            await self._record_failure(
                command=command,
                reason="evidence_unavailable",
            )
            raise

        except EvidenceRetrievalHashMismatchError:
            await self._record_failure(
                command=command,
                reason="hash_mismatch",
            )
            raise

        except EvidenceRetrievalSignatureInvalidError:
            await self._record_failure(
                command=command,
                reason="signature_invalid",
            )
            raise

        await self._record_success(
            command=command,
            retrieval=retrieval,
        )

        return retrieval

    async def _record_success(
        self,
        *,
        command: EvidenceContentAccessCommand,
        retrieval: EvidenceRetrievalResult,
    ) -> None:
        occurred_at = datetime.now(UTC)

        try:
            evidence = await self.evidence.get_by_id_for_update(command.evidence_id)

            if evidence is None:
                raise RuntimeError("Evidence disappeared before content-access persistence")

            previous = await self.custody.get_latest_for_update(evidence_id=evidence.id)

            if previous is None:
                raise RuntimeError("Evidence content access requires an existing custody record")

            metadata: dict[str, object] = {
                "correlation_id": (command.correlation_id),
                "evidence_number": (retrieval.evidence_number),
                "original_filename": (retrieval.original_filename),
                "original_sha256": (retrieval.original_sha256),
                "verified_at": (retrieval.verified_at.isoformat()),
            }

            integrity = build_custody_integrity(
                evidence_id=evidence.id,
                actor_user_id=(command.actor_user_id),
                from_user_id=None,
                to_user_id=None,
                previous_record_id=previous.id,
                previous_record_hash=(previous.record_hash),
                transfer_id=None,
                event_type=CustodyEventType.VIEWED,
                purpose=("Protected evidence content viewed"),
                source_ip=command.source_ip,
                device_identifier=(command.device_identifier),
                event_metadata=metadata,
                occurred_at=occurred_at,
            )

            signature = self.signer.sign(integrity.canonical_bytes)

            custody = await self.custody.create(
                evidence_id=evidence.id,
                actor_user_id=(command.actor_user_id),
                from_user_id=None,
                to_user_id=None,
                previous_record_id=previous.id,
                transfer_id=None,
                event_type=CustodyEventType.VIEWED,
                purpose=("Protected evidence content viewed"),
                source_ip=command.source_ip,
                device_identifier=(command.device_identifier),
                event_metadata=metadata,
                record_hash=integrity.record_hash,
                digital_signature=(signature.to_json()),
                occurred_at=occurred_at,
            )

            await self.audit.create(
                actor_user_id=(command.actor_user_id),
                action=(AuditAction.EVIDENCE_CONTENT_VIEWED),
                resource_type="evidence",
                resource_id=evidence.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(command.correlation_id),
                occurred_at=occurred_at,
                source_ip=command.source_ip,
                user_agent=command.user_agent,
                details={
                    "evidence_number": (retrieval.evidence_number),
                    "original_filename": (retrieval.original_filename),
                    "original_sha256": (retrieval.original_sha256),
                    "custody_record_id": str(custody.id),
                },
            )

            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise

    async def _record_failure(
        self,
        *,
        command: EvidenceContentAccessCommand,
        reason: str,
    ) -> None:
        occurred_at = datetime.now(UTC)

        try:
            await self.audit.create(
                actor_user_id=(command.actor_user_id),
                action=(AuditAction.EVIDENCE_CONTENT_VIEWED),
                resource_type="evidence",
                resource_id=command.evidence_id,
                outcome=AuditOutcome.FAILURE,
                correlation_id=(command.correlation_id),
                occurred_at=occurred_at,
                source_ip=command.source_ip,
                user_agent=command.user_agent,
                details={
                    "reason": reason,
                },
            )

            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise
