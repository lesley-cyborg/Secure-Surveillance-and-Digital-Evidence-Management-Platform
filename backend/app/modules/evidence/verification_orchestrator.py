from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceType,
    VerificationStatus,
)
from app.db.models.evidence import (
    Evidence,
    EvidenceKey,
)
from app.modules.evidence.errors import (
    EvidenceAuthenticationError,
    EvidenceEnvelopeError,
    EvidenceEnvelopeIntegrityError,
    EvidenceKeyUnwrapError,
    EvidenceManifestMismatchError,
    EvidenceObjectNotFoundError,
    EvidenceRetrievalHashMismatchError,
    EvidenceRetrievalSignatureInvalidError,
    EvidenceRetrievalUnavailableError,
    EvidenceStorageConfigurationError,
    EvidenceStorageUnavailableError,
    EvidenceVerificationReferenceError,
)
from app.modules.evidence.forensics import (
    EvidenceForensicManifest,
    ForensicManifestArtifact,
    build_manifest_artifact,
)
from app.modules.evidence.key_wrapping import (
    EvidenceKeyWrapper,
)
from app.modules.evidence.repository import (
    EvidenceRepository,
)
from app.modules.evidence.signing import (
    ForensicSigner,
)
from app.modules.evidence.storage import (
    EvidenceObjectStorage,
)
from app.modules.evidence.verification import (
    EvidenceRetrievalResult,
    EvidenceVerificationCommand,
    EvidenceVerificationResult,
    decrypt_persisted_evidence,
    verify_encrypted_evidence_digest,
    verify_evidence_content,
    verify_evidence_signature,
)
from app.modules.evidence.verification_service import (
    EvidenceVerificationPersistenceService,
)


@dataclass(
    frozen=True,
    slots=True,
)
class PersistedEvidenceVerificationMaterial:
    evidence_id: UUID
    evidence_number: str

    incident_id: UUID
    source_detection_id: UUID | None

    source_type: EvidenceSourceType
    evidence_type: EvidenceType

    original_filename: str
    mime_type: str
    file_size_bytes: int

    storage_bucket: str
    storage_object_key: str
    storage_version_id: str | None

    original_sha256: str
    encrypted_sha256: str
    manifest_sha256: str
    digital_signature: str

    captured_at: datetime
    ingested_at: datetime


@dataclass(
    frozen=True,
    slots=True,
)
class PersistedEvidenceKeyMaterial:
    algorithm: str
    wrapped_key: str
    key_reference: str
    key_version: int


@dataclass(
    frozen=True,
    slots=True,
)
class ForensicVerificationEvaluation:
    evidence: PersistedEvidenceVerificationMaterial

    status: VerificationStatus

    expected_sha256: str
    calculated_sha256: str | None

    hash_matches: bool
    signature_valid: bool

    failure_reason: str | None

    plaintext: bytes | None


class EvidenceVerificationOrchestrator:
    """
    Coordinate forensic verification and protected retrieval.

    Database reads are completed and the read transaction is released
    before MinIO or cryptographic work begins.

    Verification persistence occurs afterwards through
    EvidenceVerificationPersistenceService.

    Plaintext retrieval uses the same forensic evaluation pipeline and
    returns content only after a VERIFIED result has been persisted.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        storage: EvidenceObjectStorage,
        key_wrapper: EvidenceKeyWrapper,
        signer: ForensicSigner,
    ) -> None:
        self.session = session
        self.storage = storage
        self.key_wrapper = key_wrapper
        self.signer = signer

        self.evidence = EvidenceRepository(session)

        self.persistence = EvidenceVerificationPersistenceService(
            session=session,
            signer=signer,
        )

    async def verify(
        self,
        *,
        command: EvidenceVerificationCommand,
    ) -> EvidenceVerificationResult:
        evaluation = await self._evaluate(
            evidence_id=command.evidence_id,
        )

        return await self._record_evaluation(
            command=command,
            evaluation=evaluation,
        )

    async def retrieve(
        self,
        *,
        command: EvidenceVerificationCommand,
    ) -> EvidenceRetrievalResult:
        evaluation = await self._evaluate(
            evidence_id=command.evidence_id,
        )

        persisted = await self._record_evaluation(
            command=command,
            evaluation=evaluation,
        )

        if evaluation.status is VerificationStatus.UNAVAILABLE:
            raise EvidenceRetrievalUnavailableError(
                evaluation.failure_reason or "Evidence is unavailable."
            )

        if evaluation.status is VerificationStatus.SIGNATURE_INVALID:
            raise EvidenceRetrievalSignatureInvalidError(
                evaluation.failure_reason or ("Evidence authenticity verification failed.")
            )

        if evaluation.status is VerificationStatus.HASH_MISMATCH:
            raise EvidenceRetrievalHashMismatchError(
                evaluation.failure_reason or ("Evidence integrity verification failed.")
            )

        if evaluation.status is not VerificationStatus.VERIFIED:
            raise RuntimeError("Unexpected evidence verification status")

        if evaluation.plaintext is None:
            raise RuntimeError("Verified evidence has no plaintext")

        evidence = evaluation.evidence

        return EvidenceRetrievalResult(
            evidence_id=evidence.evidence_id,
            evidence_number=evidence.evidence_number,
            original_filename=(evidence.original_filename),
            mime_type=evidence.mime_type,
            content=evaluation.plaintext,
            original_sha256=(evidence.original_sha256),
            verified_at=persisted.verified_at,
        )

    async def _evaluate(
        self,
        *,
        evidence_id: UUID,
    ) -> ForensicVerificationEvaluation:
        evidence, key = await self._load_material(
            evidence_id=evidence_id,
        )

        if key is None:
            return ForensicVerificationEvaluation(
                evidence=evidence,
                status=VerificationStatus.UNAVAILABLE,
                expected_sha256=(evidence.encrypted_sha256),
                calculated_sha256=None,
                hash_matches=False,
                signature_valid=False,
                failure_reason=("Evidence decryption key is unavailable."),
                plaintext=None,
            )

        try:
            encrypted_payload = await self.storage.get_object(
                object_key=(evidence.storage_object_key),
                version_id=(evidence.storage_version_id),
            )

        except EvidenceObjectNotFoundError:
            return ForensicVerificationEvaluation(
                evidence=evidence,
                status=VerificationStatus.UNAVAILABLE,
                expected_sha256=(evidence.encrypted_sha256),
                calculated_sha256=None,
                hash_matches=False,
                signature_valid=False,
                failure_reason=("Evidence object was not found in object storage."),
                plaintext=None,
            )

        except (
            EvidenceStorageUnavailableError,
            EvidenceStorageConfigurationError,
        ):
            return ForensicVerificationEvaluation(
                evidence=evidence,
                status=VerificationStatus.UNAVAILABLE,
                expected_sha256=(evidence.encrypted_sha256),
                calculated_sha256=None,
                hash_matches=False,
                signature_valid=False,
                failure_reason=("Evidence object storage is unavailable."),
                plaintext=None,
            )

        digest = verify_encrypted_evidence_digest(
            encrypted_payload=encrypted_payload,
            expected_sha256=(evidence.encrypted_sha256),
        )

        if not digest.matches:
            return ForensicVerificationEvaluation(
                evidence=evidence,
                status=(VerificationStatus.HASH_MISMATCH),
                expected_sha256=(digest.expected_sha256),
                calculated_sha256=(digest.calculated_sha256),
                hash_matches=False,
                signature_valid=False,
                failure_reason=("Stored encrypted evidence SHA-256 does not match."),
                plaintext=None,
            )

        signature = verify_evidence_signature(
            signer=self.signer,
            digital_signature=(evidence.digital_signature),
            evidence_number=(evidence.evidence_number),
            incident_id=evidence.incident_id,
            source_detection_id=(evidence.source_detection_id),
            storage_bucket=(evidence.storage_bucket),
            storage_object_key=(evidence.storage_object_key),
            storage_version_id=(evidence.storage_version_id),
            original_sha256=(evidence.original_sha256),
            encrypted_sha256=(evidence.encrypted_sha256),
            manifest_sha256=(evidence.manifest_sha256),
            captured_at=evidence.captured_at,
            ingested_at=evidence.ingested_at,
        )

        if not signature.signature_valid:
            return ForensicVerificationEvaluation(
                evidence=evidence,
                status=(VerificationStatus.SIGNATURE_INVALID),
                expected_sha256=(digest.expected_sha256),
                calculated_sha256=(digest.calculated_sha256),
                hash_matches=True,
                signature_valid=False,
                failure_reason=(
                    signature.failure_reason or ("Stored digital signature verification failed.")
                ),
                plaintext=None,
            )

        manifest = self._build_manifest(evidence)

        try:
            decrypted = decrypt_persisted_evidence(
                encrypted_payload=(encrypted_payload),
                encrypted_sha256=(evidence.encrypted_sha256),
                wrapped_key_algorithm=(key.algorithm),
                wrapped_key_value=(key.wrapped_key),
                key_reference=key.key_reference,
                key_version=key.key_version,
                manifest=manifest,
                key_wrapper=self.key_wrapper,
            )

        except EvidenceKeyUnwrapError:
            return ForensicVerificationEvaluation(
                evidence=evidence,
                status=VerificationStatus.UNAVAILABLE,
                expected_sha256=(digest.expected_sha256),
                calculated_sha256=(digest.calculated_sha256),
                hash_matches=False,
                signature_valid=True,
                failure_reason=("Evidence decryption key could not be recovered."),
                plaintext=None,
            )

        except (
            EvidenceEnvelopeIntegrityError,
            EvidenceEnvelopeError,
            EvidenceAuthenticationError,
            EvidenceManifestMismatchError,
        ):
            return ForensicVerificationEvaluation(
                evidence=evidence,
                status=(VerificationStatus.HASH_MISMATCH),
                expected_sha256=(digest.expected_sha256),
                calculated_sha256=(digest.calculated_sha256),
                hash_matches=False,
                signature_valid=True,
                failure_reason=("Encrypted evidence failed authenticated integrity verification."),
                plaintext=None,
            )

        content = verify_evidence_content(
            plaintext=decrypted.content,
            expected_original_sha256=(evidence.original_sha256),
            manifest=manifest,
            expected_manifest_sha256=(evidence.manifest_sha256),
        )

        if not content.matches:
            return ForensicVerificationEvaluation(
                evidence=evidence,
                status=(VerificationStatus.HASH_MISMATCH),
                expected_sha256=(digest.expected_sha256),
                calculated_sha256=(digest.calculated_sha256),
                hash_matches=False,
                signature_valid=True,
                failure_reason=(
                    "Decrypted evidence or forensic manifest integrity verification failed."
                ),
                plaintext=None,
            )

        return ForensicVerificationEvaluation(
            evidence=evidence,
            status=VerificationStatus.VERIFIED,
            expected_sha256=(digest.expected_sha256),
            calculated_sha256=(digest.calculated_sha256),
            hash_matches=True,
            signature_valid=True,
            failure_reason=None,
            plaintext=decrypted.content,
        )

    async def _load_material(
        self,
        *,
        evidence_id: UUID,
    ) -> tuple[
        PersistedEvidenceVerificationMaterial,
        PersistedEvidenceKeyMaterial | None,
    ]:
        try:
            evidence = await self.evidence.get_by_id(evidence_id)

            if evidence is None:
                raise EvidenceVerificationReferenceError("Evidence does not exist.")

            evidence_material = self._snapshot_evidence(evidence)

            active_key = await self.evidence.get_active_key(evidence_id)

            key_material = self._snapshot_key(active_key) if active_key is not None else None

            return (
                evidence_material,
                key_material,
            )

        finally:
            # Do not retain a PostgreSQL transaction while
            # calling MinIO or performing RSA/AES work.
            if self.session.in_transaction():
                await self.session.rollback()

    @staticmethod
    def _snapshot_evidence(
        evidence: Evidence,
    ) -> PersistedEvidenceVerificationMaterial:
        return PersistedEvidenceVerificationMaterial(
            evidence_id=evidence.id,
            evidence_number=(evidence.evidence_number),
            incident_id=evidence.incident_id,
            source_detection_id=(evidence.source_detection_id),
            source_type=evidence.source_type,
            evidence_type=evidence.evidence_type,
            original_filename=(evidence.original_filename),
            mime_type=evidence.mime_type,
            file_size_bytes=(evidence.file_size_bytes),
            storage_bucket=(evidence.storage_bucket),
            storage_object_key=(evidence.storage_object_key),
            storage_version_id=(evidence.storage_version_id),
            original_sha256=(evidence.original_sha256),
            encrypted_sha256=(evidence.encrypted_sha256),
            manifest_sha256=(evidence.manifest_sha256),
            digital_signature=(evidence.digital_signature),
            captured_at=evidence.captured_at,
            ingested_at=evidence.ingested_at,
        )

    @staticmethod
    def _snapshot_key(
        key: EvidenceKey,
    ) -> PersistedEvidenceKeyMaterial:
        return PersistedEvidenceKeyMaterial(
            algorithm=key.algorithm,
            wrapped_key=key.wrapped_key,
            key_reference=key.key_reference,
            key_version=key.key_version,
        )

    @staticmethod
    def _build_manifest(
        evidence: PersistedEvidenceVerificationMaterial,
    ) -> ForensicManifestArtifact:
        manifest = EvidenceForensicManifest(
            evidence_number=(evidence.evidence_number),
            incident_id=evidence.incident_id,
            source_detection_id=(evidence.source_detection_id),
            source_type=evidence.source_type,
            evidence_type=evidence.evidence_type,
            original_filename=(evidence.original_filename),
            mime_type=evidence.mime_type,
            file_size_bytes=(evidence.file_size_bytes),
            original_sha256=(evidence.original_sha256),
            captured_at=evidence.captured_at,
        )

        return build_manifest_artifact(manifest)

    async def _record_evaluation(
        self,
        *,
        command: EvidenceVerificationCommand,
        evaluation: ForensicVerificationEvaluation,
    ) -> EvidenceVerificationResult:
        return await self.persistence.record(
            command=command,
            verification_status=(evaluation.status),
            expected_sha256=(evaluation.expected_sha256),
            calculated_sha256=(evaluation.calculated_sha256),
            hash_matches=(evaluation.hash_matches),
            signature_valid=(evaluation.signature_valid),
            failure_reason=(evaluation.failure_reason),
            verified_at=datetime.now(UTC),
        )
