from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
    VerificationStatus,
)
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
from app.modules.evidence.verification import (
    EvidenceVerificationCommand,
    EvidenceVerificationResult,
    evidence_status_after_verification,
)


class EvidenceVerificationPersistenceService:
    """
    Persist one completed evidence-verification outcome.

    Cryptographic and object-storage verification must be completed
    before entering this service so PostgreSQL row locks remain short.
    """

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

    async def record(
        self,
        *,
        command: EvidenceVerificationCommand,
        verification_status: VerificationStatus,
        expected_sha256: str,
        calculated_sha256: str | None,
        hash_matches: bool,
        signature_valid: bool,
        failure_reason: str | None,
        verified_at: datetime,
    ) -> EvidenceVerificationResult:
        try:
            evidence = await self.evidence.get_by_id_for_update(command.evidence_id)

            if evidence is None:
                raise RuntimeError("Evidence disappeared before verification persistence")

            verification = await self.evidence.create_verification(
                evidence_id=evidence.id,
                verified_by_user_id=(command.verified_by_user_id),
                idempotency_key=(command.idempotency_key),
                expected_sha256=expected_sha256,
                calculated_sha256=(calculated_sha256),
                hash_matches=hash_matches,
                signature_valid=signature_valid,
                verification_status=(verification_status),
                failure_reason=failure_reason,
                verified_at=verified_at,
            )

            next_status = evidence_status_after_verification(
                current_status=evidence.status,
                verification_status=(verification_status),
            )

            await self.evidence.set_status(
                evidence=evidence,
                status=next_status,
            )

            custody_record_id = None

            if verification_status is VerificationStatus.VERIFIED:
                previous_custody = await self.custody.get_latest_for_update(evidence_id=evidence.id)

                if previous_custody is None:
                    raise RuntimeError("Verified evidence must have an existing custody record")

                custody_metadata: dict[
                    str,
                    object,
                ] = {
                    "correlation_id": (command.correlation_id),
                    "verification_id": str(verification.id),
                    "evidence_number": (evidence.evidence_number),
                    "verification_status": (verification_status.value),
                    "expected_sha256": (expected_sha256),
                    "calculated_sha256": (calculated_sha256),
                    "hash_matches": hash_matches,
                    "signature_valid": (signature_valid),
                }

                custody_integrity = build_custody_integrity(
                    evidence_id=evidence.id,
                    actor_user_id=(command.verified_by_user_id),
                    from_user_id=None,
                    to_user_id=None,
                    previous_record_id=(previous_custody.id),
                    previous_record_hash=(previous_custody.record_hash),
                    transfer_id=None,
                    event_type=(CustodyEventType.VERIFIED),
                    purpose=("Evidence integrity and authenticity verified"),
                    source_ip=(command.source_ip),
                    device_identifier=(command.device_identifier),
                    event_metadata=(custody_metadata),
                    occurred_at=verified_at,
                )

                custody_signature = self.signer.sign(custody_integrity.canonical_bytes)

                custody_record = await self.custody.create(
                    evidence_id=evidence.id,
                    actor_user_id=(command.verified_by_user_id),
                    from_user_id=None,
                    to_user_id=None,
                    previous_record_id=(previous_custody.id),
                    transfer_id=None,
                    event_type=(CustodyEventType.VERIFIED),
                    purpose=("Evidence integrity and authenticity verified"),
                    source_ip=(command.source_ip),
                    device_identifier=(command.device_identifier),
                    event_metadata=(custody_metadata),
                    record_hash=(custody_integrity.record_hash),
                    digital_signature=(custody_signature.to_json()),
                    occurred_at=verified_at,
                )

                custody_record_id = custody_record.id

            audit_outcome = (
                AuditOutcome.SUCCESS
                if verification_status is VerificationStatus.VERIFIED
                else AuditOutcome.FAILURE
            )

            audit_log = await self.audit.create(
                actor_user_id=(command.verified_by_user_id),
                action=(AuditAction.EVIDENCE_VERIFIED),
                resource_type="evidence",
                resource_id=evidence.id,
                outcome=audit_outcome,
                correlation_id=(command.correlation_id),
                occurred_at=verified_at,
                source_ip=command.source_ip,
                user_agent=command.user_agent,
                details={
                    "verification_id": str(verification.id),
                    "evidence_number": (evidence.evidence_number),
                    "verification_status": (verification_status.value),
                    "expected_sha256": (expected_sha256),
                    "calculated_sha256": (calculated_sha256),
                    "hash_matches": (hash_matches),
                    "signature_valid": (signature_valid),
                    "failure_reason": (failure_reason),
                    "custody_record_id": (
                        str(custody_record_id) if custody_record_id is not None else None
                    ),
                },
            )

            result = EvidenceVerificationResult(
                evidence_id=evidence.id,
                verification_id=verification.id,
                verification_status=(verification_status),
                expected_sha256=(expected_sha256),
                calculated_sha256=(calculated_sha256),
                hash_matches=hash_matches,
                signature_valid=(signature_valid),
                verified_at=verified_at,
                failure_reason=failure_reason,
                custody_record_id=(custody_record_id),
                audit_log_id=audit_log.id,
            )

            await self.session.commit()

            return result

        except Exception:
            await self.session.rollback()
            raise
