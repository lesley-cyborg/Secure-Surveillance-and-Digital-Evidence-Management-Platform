from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceType,
)
from app.modules.evidence.crypto import (
    SecuredEvidenceArtifact,
    decrypt_evidence,
    secure_evidence,
)
from app.modules.evidence.errors import (
    EvidenceAuthenticationError,
    EvidenceEnvelopeError,
    EvidenceEnvelopeIntegrityError,
    EvidenceKeyUnwrapError,
    EvidenceKeyWrapError,
    EvidenceManifestMismatchError,
)
from app.modules.evidence.forensics import (
    EvidenceForensicManifest,
    ForensicManifestArtifact,
    build_manifest_artifact,
)
from app.modules.evidence.key_wrapping import (
    RSAOAEPKeyWrapper,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)

_INCIDENT_ID = UUID("11111111-1111-1111-1111-111111111111")

_DETECTION_ID = UUID("22222222-2222-2222-2222-222222222222")

_CAPTURED_AT = datetime(
    2026,
    8,
    8,
    12,
    30,
    45,
    tzinfo=UTC,
)

_CONTENT = b"secure-surveillance-forensic-evidence"


def create_manifest(
    *,
    content: bytes = _CONTENT,
    original_filename: str = ("camera-frame.jpg"),
) -> ForensicManifestArtifact:
    manifest = EvidenceForensicManifest(
        evidence_number=("EVD-20260808-123045-ABCDEF123456"),
        incident_id=_INCIDENT_ID,
        source_detection_id=_DETECTION_ID,
        source_type=(EvidenceSourceType.AI_CAPTURE),
        evidence_type=EvidenceType.IMAGE,
        original_filename=(original_filename),
        mime_type="image/jpeg",
        file_size_bytes=len(content),
        original_sha256=(hashlib.sha256(content).hexdigest()),
        captured_at=_CAPTURED_AT,
    )

    return build_manifest_artifact(manifest)


@pytest.fixture(scope="module")
def key_wrapper() -> RSAOAEPKeyWrapper:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    return RSAOAEPKeyWrapper(
        public_key=(private_key.public_key()),
        private_key=private_key,
        key_reference=("test://evidence-rsa/v1"),
        key_version=1,
    )


def test_secure_evidence_round_trip(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    manifest = create_manifest()

    artifact = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    assert artifact.encrypted_payload != _CONTENT

    assert artifact.encrypted_sha256 == hashlib.sha256(artifact.encrypted_payload).hexdigest()

    assert artifact.algorithm == "AES-256-GCM"

    assert artifact.wrapped_key.algorithm == "RSA-OAEP-SHA256"

    decrypted = decrypt_evidence(
        artifact,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    assert decrypted == _CONTENT


def test_repeated_encryption_is_nondeterministic(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    manifest = create_manifest()

    first = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    second = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    assert first.encrypted_payload != second.encrypted_payload

    assert first.wrapped_key.wrapped_key != second.wrapped_key.wrapped_key


def test_manifest_is_authenticated_as_aad(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    original_manifest = create_manifest()

    artifact = secure_evidence(
        _CONTENT,
        manifest=original_manifest,
        key_wrapper=key_wrapper,
    )

    changed_manifest = create_manifest(original_filename=("modified-frame.jpg"))

    with pytest.raises(EvidenceAuthenticationError):
        decrypt_evidence(
            artifact,
            manifest=changed_manifest,
            key_wrapper=key_wrapper,
        )


def test_encrypted_digest_detects_storage_tampering(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    manifest = create_manifest()

    artifact = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    corrupted = bytearray(artifact.encrypted_payload)

    corrupted[-1] ^= 0x01

    tampered = SecuredEvidenceArtifact(
        encrypted_payload=bytes(corrupted),
        encrypted_sha256=(artifact.encrypted_sha256),
        wrapped_key=(artifact.wrapped_key),
    )

    with pytest.raises(EvidenceEnvelopeIntegrityError):
        decrypt_evidence(
            tampered,
            manifest=manifest,
            key_wrapper=key_wrapper,
        )


def test_gcm_detects_authenticated_tampering(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    manifest = create_manifest()

    artifact = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    corrupted = bytearray(artifact.encrypted_payload)

    corrupted[-1] ^= 0x01

    corrupted_bytes = bytes(corrupted)

    tampered = SecuredEvidenceArtifact(
        encrypted_payload=(corrupted_bytes),
        encrypted_sha256=(hashlib.sha256(corrupted_bytes).hexdigest()),
        wrapped_key=(artifact.wrapped_key),
    )

    with pytest.raises(EvidenceAuthenticationError):
        decrypt_evidence(
            tampered,
            manifest=manifest,
            key_wrapper=key_wrapper,
        )


def test_content_must_match_manifest(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    manifest = create_manifest()

    with pytest.raises(EvidenceManifestMismatchError):
        secure_evidence(
            b"different-evidence",
            manifest=manifest,
            key_wrapper=key_wrapper,
        )


def test_rsa_wrapper_round_trip(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    dek = bytes(range(32))

    wrapped = key_wrapper.wrap_key(dek)

    recovered = key_wrapper.unwrap_key(wrapped)

    assert recovered == dek


def test_rsa_wrapper_rejects_wrong_dek_length(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    with pytest.raises(EvidenceKeyWrapError):
        key_wrapper.wrap_key(b"too-short")


def test_wrong_rsa_key_cannot_unwrap(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    wrapped = key_wrapper.wrap_key(bytes(range(32)))

    other_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    other_wrapper = RSAOAEPKeyWrapper(
        public_key=(other_private_key.public_key()),
        private_key=other_private_key,
        key_reference=("test://evidence-rsa/v1"),
        key_version=1,
    )

    with pytest.raises(EvidenceKeyUnwrapError):
        other_wrapper.unwrap_key(wrapped)


def test_unknown_envelope_version_is_rejected(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    manifest = create_manifest()

    artifact = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    corrupted = bytearray(artifact.encrypted_payload)

    # Envelope:
    # bytes 0..3 = SSPE
    # byte 4     = version
    corrupted[4] = 99

    corrupted_bytes = bytes(corrupted)

    tampered = SecuredEvidenceArtifact(
        encrypted_payload=(corrupted_bytes),
        encrypted_sha256=(hashlib.sha256(corrupted_bytes).hexdigest()),
        wrapped_key=(artifact.wrapped_key),
    )

    with pytest.raises(EvidenceEnvelopeError):
        decrypt_evidence(
            tampered,
            manifest=manifest,
            key_wrapper=key_wrapper,
        )
