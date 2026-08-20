from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import VerificationStatus
from app.db.models.evidence import (
    EvidenceVerification,
)
from app.modules.evidence.repository import (
    EvidenceRepository,
)
from app.modules.evidence.verification import (
    EvidenceVerificationCommand,
    EvidenceVerificationResult,
)
from app.modules.evidence.verification_orchestrator import (
    EvidenceVerificationOrchestrator,
)


class EvidenceVerificationNotFoundError(LookupError):
    """Requested evidence does not exist."""


class EvidenceVerificationResponse(BaseModel):
    """Public HTTP representation of one verification."""

    model_config = ConfigDict(
        populate_by_name=True,
    )

    id: UUID

    evidence_id: UUID = Field(
        alias="evidenceId",
    )

    verified_by_user_id: UUID | None = Field(
        alias="verifiedByUserId",
    )

    expected_sha256: str = Field(
        alias="expectedSha256",
    )

    calculated_sha256: str | None = Field(
        alias="calculatedSha256",
    )

    hash_matches: bool = Field(
        alias="hashMatches",
    )

    signature_valid: bool = Field(
        alias="signatureValid",
    )

    verification_status: VerificationStatus = Field(
        alias="verificationStatus",
    )

    failure_reason: str | None = Field(
        alias="failureReason",
    )

    verified_at: datetime = Field(
        alias="verifiedAt",
    )

    @classmethod
    def from_domain_result(
        cls,
        *,
        result: EvidenceVerificationResult,
        verified_by_user_id: UUID | None,
    ) -> EvidenceVerificationResponse:
        return cls(
            id=result.verification_id,
            evidence_id=result.evidence_id,
            verified_by_user_id=verified_by_user_id,
            expected_sha256=result.expected_sha256,
            calculated_sha256=(result.calculated_sha256),
            hash_matches=result.hash_matches,
            signature_valid=(result.signature_valid),
            verification_status=(result.verification_status),
            failure_reason=result.failure_reason,
            verified_at=result.verified_at,
        )

    @classmethod
    def from_persisted(
        cls,
        verification: EvidenceVerification,
    ) -> EvidenceVerificationResponse:
        return cls(
            id=verification.id,
            evidence_id=verification.evidence_id,
            verified_by_user_id=(verification.verified_by_user_id),
            expected_sha256=(verification.expected_sha256),
            calculated_sha256=(verification.calculated_sha256),
            hash_matches=(verification.hash_matches),
            signature_valid=(verification.signature_valid),
            verification_status=(verification.verification_status),
            failure_reason=(verification.failure_reason),
            verified_at=verification.verified_at,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceVerificationHTTPOutcome:
    verification: EvidenceVerificationResponse
    replayed: bool


class EvidenceVerificationHTTPService:
    """HTTP-facing verification/idempotency coordinator.

    The cryptographic verification itself remains in
    EvidenceVerificationOrchestrator.

    This layer is responsible only for:

    - HTTP idempotency semantics.
    - evidence existence checks.
    - translating persisted/domain verification data into
      the HTTP representation.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        orchestrator: EvidenceVerificationOrchestrator,
        repository: EvidenceRepository | None = None,
    ) -> None:
        self.session = session
        self.orchestrator = orchestrator

        self.evidence = repository if repository is not None else EvidenceRepository(session)

    async def verify(
        self,
        *,
        command: EvidenceVerificationCommand,
    ) -> EvidenceVerificationHTTPOutcome:
        idempotency_key = command.idempotency_key

        if idempotency_key is None:
            raise ValueError("HTTP verification requires an idempotency key")

        existing = await self.evidence.get_verification_by_idempotency_key(
            evidence_id=command.evidence_id,
            idempotency_key=idempotency_key,
        )

        if existing is not None:
            await self.session.rollback()

            return EvidenceVerificationHTTPOutcome(
                verification=(EvidenceVerificationResponse.from_persisted(existing)),
                replayed=True,
            )

        evidence = await self.evidence.get_by_id(command.evidence_id)

        if evidence is None:
            await self.session.rollback()

            raise EvidenceVerificationNotFoundError("Evidence does not exist")

        # Finish the HTTP preflight read transaction before
        # the orchestrator performs storage and cryptographic
        # work. The orchestrator/persistence layer owns the
        # verification transaction itself.
        await self.session.rollback()

        try:
            result = await self.orchestrator.verify(command=command)

        except IntegrityError:
            # A concurrent request may have used the same
            # (evidence_id, idempotency_key) after our
            # preflight query but before persistence.
            await self.session.rollback()

            existing = await self.evidence.get_verification_by_idempotency_key(
                evidence_id=command.evidence_id,
                idempotency_key=idempotency_key,
            )

            if existing is None:
                # The IntegrityError was unrelated to the
                # idempotency uniqueness constraint.
                raise

            await self.session.rollback()

            return EvidenceVerificationHTTPOutcome(
                verification=(EvidenceVerificationResponse.from_persisted(existing)),
                replayed=True,
            )

        return EvidenceVerificationHTTPOutcome(
            verification=(
                EvidenceVerificationResponse.from_domain_result(
                    result=result,
                    verified_by_user_id=(command.verified_by_user_id),
                )
            ),
            replayed=False,
        )
