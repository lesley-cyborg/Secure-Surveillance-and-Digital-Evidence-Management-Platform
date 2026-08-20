from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.db.models.enums import (
    EvidenceStatus,
    VerificationStatus,
)
from app.modules.evidence.crypto import (
    SecuredEvidenceArtifact,
    decrypt_evidence,
)
from app.modules.evidence.errors import (
    EvidenceSignatureFormatError,
)
from app.modules.evidence.forensics import (
    ForensicManifestArtifact,
    sha256_bytes,
)
from app.modules.evidence.key_wrapping import (
    EvidenceKeyWrapper,
    WrappedEvidenceKey,
)
from app.modules.evidence.signing import (
    DigitalSignatureEnvelope,
    ForensicSigner,
    build_evidence_signature_payload,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceVerificationCommand:
    """
    Request verification of one persisted evidence artifact.

    The service will load Evidence + its active EvidenceKey,
    retrieve the exact MinIO object version, verify its
    forensic integrity, and persist one EvidenceVerification.
    """

    evidence_id: UUID

    verified_by_user_id: UUID | None

    correlation_id: str

    source_ip: str | None = None

    user_agent: str | None = None

    device_identifier: str | None = None

    idempotency_key: str | None = None

    def __post_init__(
        self,
    ) -> None:
        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty")

        if self.idempotency_key is not None:
            if not (16 <= len(self.idempotency_key) <= 255):
                raise ValueError("idempotency_key must contain between 16 and 255 characters")


@dataclass(
    frozen=True,
    slots=True,
)
class EncryptedEvidenceDigestResult:
    """Result of validating a stored encrypted evidence object."""

    expected_sha256: str
    calculated_sha256: str
    matches: bool

    def __post_init__(
        self,
    ) -> None:
        _validate_sha256(
            field_name="expected_sha256",
            value=self.expected_sha256,
        )

        _validate_sha256(
            field_name="calculated_sha256",
            value=self.calculated_sha256,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceVerificationResult:
    evidence_id: UUID

    verification_id: UUID

    verification_status: VerificationStatus

    expected_sha256: str

    calculated_sha256: str | None

    hash_matches: bool

    signature_valid: bool

    verified_at: datetime

    failure_reason: str | None

    custody_record_id: UUID | None

    audit_log_id: UUID

    def __post_init__(
        self,
    ) -> None:
        _validate_sha256(
            field_name="expected_sha256",
            value=self.expected_sha256,
        )

        if self.calculated_sha256 is not None:
            _validate_sha256(
                field_name=("calculated_sha256"),
                value=(self.calculated_sha256),
            )

        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("verified_at must be timezone-aware")

        if self.verification_status is VerificationStatus.VERIFIED:
            if not self.hash_matches:
                raise ValueError("VERIFIED requires hash_matches=True")

            if not self.signature_valid:
                raise ValueError("VERIFIED requires signature_valid=True")

            if self.calculated_sha256 is None:
                raise ValueError("VERIFIED requires calculated_sha256")

            if self.failure_reason is not None:
                raise ValueError("VERIFIED must not have a failure_reason")

            if self.custody_record_id is None:
                raise ValueError("VERIFIED requires a VERIFIED custody record")


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceSignatureVerificationResult:
    """Result of validating the persisted evidence signature."""

    signature_valid: bool
    signature_format_valid: bool
    failure_reason: str | None

    def __post_init__(
        self,
    ) -> None:
        if self.signature_valid:
            if not self.signature_format_valid:
                raise ValueError("A valid signature requires signature_format_valid=True")

            if self.failure_reason is not None:
                raise ValueError("A valid signature must not have a failure_reason")

        if not self.signature_format_valid:
            if self.signature_valid:
                raise ValueError("An invalid signature format cannot have signature_valid=True")

            if self.failure_reason is None:
                raise ValueError("An invalid signature format requires a failure_reason")


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceRetrievalResult:
    """
    Plaintext returned only after successful forensic
    verification and authenticated decryption.
    """

    evidence_id: UUID

    evidence_number: str

    original_filename: str

    mime_type: str | None

    content: bytes = field(repr=False)

    original_sha256: str

    verified_at: datetime

    def __post_init__(
        self,
    ) -> None:
        if not self.evidence_number.strip():
            raise ValueError("evidence_number must not be empty")

        if not self.original_filename.strip():
            raise ValueError("original_filename must not be empty")

        if not self.content:
            raise ValueError("content must not be empty")

        _validate_sha256(
            field_name="original_sha256",
            value=self.original_sha256,
        )

        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("verified_at must be timezone-aware")


@dataclass(
    frozen=True,
    slots=True,
)
class VerifiedEvidence:
    """
    Internal service output combining the forensic
    verification record and verified plaintext.

    Plaintext remains repr-hidden.
    """

    verification: EvidenceVerificationResult

    retrieval: EvidenceRetrievalResult


def verify_encrypted_evidence_digest(
    *,
    encrypted_payload: bytes,
    expected_sha256: str,
) -> EncryptedEvidenceDigestResult:
    """
    Calculate and compare the SHA-256 digest of the exact encrypted
    bytes retrieved from object storage.

    This step intentionally performs no key unwrap or decryption.
    """

    _validate_sha256(
        field_name="expected_sha256",
        value=expected_sha256,
    )

    calculated_sha256 = hashlib.sha256(encrypted_payload).hexdigest()

    return EncryptedEvidenceDigestResult(
        expected_sha256=expected_sha256,
        calculated_sha256=calculated_sha256,
        matches=hmac.compare_digest(
            calculated_sha256,
            expected_sha256,
        ),
    )


def verify_evidence_signature(
    *,
    signer: ForensicSigner,
    digital_signature: str,
    evidence_number: str,
    incident_id: UUID,
    source_detection_id: UUID | None,
    storage_bucket: str,
    storage_object_key: str,
    storage_version_id: str | None,
    original_sha256: str,
    encrypted_sha256: str,
    manifest_sha256: str,
    captured_at: datetime,
    ingested_at: datetime,
) -> EvidenceSignatureVerificationResult:
    """
    Rebuild and verify the canonical storage-bound signature payload
    represented by one persisted Evidence row.
    """

    signature_payload = build_evidence_signature_payload(
        evidence_number=evidence_number,
        incident_id=incident_id,
        source_detection_id=(source_detection_id),
        storage_bucket=storage_bucket,
        storage_object_key=(storage_object_key),
        storage_version_id=(storage_version_id),
        original_sha256=(original_sha256),
        encrypted_sha256=(encrypted_sha256),
        manifest_sha256=(manifest_sha256),
        captured_at=captured_at,
        ingested_at=ingested_at,
    )

    try:
        signature = DigitalSignatureEnvelope.from_json(digital_signature)
    except EvidenceSignatureFormatError:
        return EvidenceSignatureVerificationResult(
            signature_valid=False,
            signature_format_valid=False,
            failure_reason=("Stored digital signature envelope is invalid."),
        )

    signature_valid = signer.verify(
        signature_payload,
        signature,
    )

    return EvidenceSignatureVerificationResult(
        signature_valid=signature_valid,
        signature_format_valid=True,
        failure_reason=(
            None if signature_valid else ("Stored digital signature verification failed.")
        ),
    )


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceDecryptionResult:
    """Successfully authenticated plaintext evidence."""

    content: bytes = field(repr=False)

    def __post_init__(
        self,
    ) -> None:
        if not self.content:
            raise ValueError("Decrypted evidence content must not be empty")


def decrypt_persisted_evidence(
    *,
    encrypted_payload: bytes,
    encrypted_sha256: str,
    wrapped_key_algorithm: str,
    wrapped_key_value: str,
    key_reference: str,
    key_version: int,
    manifest: ForensicManifestArtifact,
    key_wrapper: EvidenceKeyWrapper,
) -> EvidenceDecryptionResult:
    """
    Reconstruct the persisted cryptographic artifacts and perform
    authenticated evidence decryption.

    Cryptographic domain exceptions are intentionally preserved so
    orchestration can classify them later.
    """

    wrapped_key = WrappedEvidenceKey(
        algorithm=wrapped_key_algorithm,
        wrapped_key=wrapped_key_value,
        key_reference=key_reference,
        key_version=key_version,
    )

    artifact = SecuredEvidenceArtifact(
        encrypted_payload=encrypted_payload,
        encrypted_sha256=encrypted_sha256,
        wrapped_key=wrapped_key,
    )

    plaintext = decrypt_evidence(
        artifact,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    return EvidenceDecryptionResult(content=plaintext)


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceContentVerificationResult:
    """Integrity result for decrypted evidence and its forensic manifest."""

    expected_original_sha256: str
    calculated_original_sha256: str

    expected_manifest_sha256: str
    calculated_manifest_sha256: str

    original_hash_matches: bool
    manifest_hash_matches: bool

    def __post_init__(
        self,
    ) -> None:
        _validate_sha256(
            field_name="expected_original_sha256",
            value=self.expected_original_sha256,
        )

        _validate_sha256(
            field_name="calculated_original_sha256",
            value=self.calculated_original_sha256,
        )

        _validate_sha256(
            field_name="expected_manifest_sha256",
            value=self.expected_manifest_sha256,
        )

        _validate_sha256(
            field_name="calculated_manifest_sha256",
            value=self.calculated_manifest_sha256,
        )

    @property
    def matches(
        self,
    ) -> bool:
        return self.original_hash_matches and self.manifest_hash_matches


def verify_evidence_content(
    *,
    plaintext: bytes,
    expected_original_sha256: str,
    manifest: ForensicManifestArtifact,
    expected_manifest_sha256: str,
) -> EvidenceContentVerificationResult:
    """
    Verify decrypted evidence bytes and the reconstructed canonical
    forensic manifest against their persisted SHA-256 digests.
    """

    _validate_sha256(
        field_name="expected_original_sha256",
        value=expected_original_sha256,
    )

    _validate_sha256(
        field_name="expected_manifest_sha256",
        value=expected_manifest_sha256,
    )

    calculated_original_sha256 = sha256_bytes(plaintext)

    calculated_manifest_sha256 = manifest.sha256

    return EvidenceContentVerificationResult(
        expected_original_sha256=(expected_original_sha256),
        calculated_original_sha256=(calculated_original_sha256),
        expected_manifest_sha256=(expected_manifest_sha256),
        calculated_manifest_sha256=(calculated_manifest_sha256),
        original_hash_matches=(
            hmac.compare_digest(
                calculated_original_sha256,
                expected_original_sha256,
            )
        ),
        manifest_hash_matches=(
            hmac.compare_digest(
                calculated_manifest_sha256,
                expected_manifest_sha256,
            )
        ),
    )


def evidence_status_after_verification(
    *,
    current_status: EvidenceStatus,
    verification_status: VerificationStatus,
) -> EvidenceStatus:
    """
    Determine the persisted evidence lifecycle status after verification.

    Storage unavailability does not prove compromise, so UNAVAILABLE
    preserves the current evidence status.
    """

    if verification_status is VerificationStatus.VERIFIED:
        return EvidenceStatus.VERIFIED

    if verification_status in {
        VerificationStatus.HASH_MISMATCH,
        VerificationStatus.SIGNATURE_INVALID,
    }:
        return EvidenceStatus.COMPROMISED

    if verification_status is VerificationStatus.UNAVAILABLE:
        return current_status

    raise ValueError("Unsupported verification status")


def _validate_sha256(
    *,
    field_name: str,
    value: str,
) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
