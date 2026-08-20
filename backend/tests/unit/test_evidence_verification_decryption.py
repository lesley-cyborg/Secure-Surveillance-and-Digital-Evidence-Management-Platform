from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceType,
)
from app.modules.evidence.crypto import (
    secure_evidence,
)
from app.modules.evidence.errors import (
    EvidenceAuthenticationError,
    EvidenceKeyUnwrapError,
)
from app.modules.evidence.forensics import (
    EvidenceForensicManifest,
    ForensicManifestArtifact,
    build_manifest_artifact,
)
from app.modules.evidence.key_wrapping import (
    RSAOAEPKeyWrapper,
)
from app.modules.evidence.verification import (
    EvidenceDecryptionResult,
    decrypt_persisted_evidence,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)

_CONTENT = b"phase-6.2i.5-authenticated-evidence"


def create_key_wrapper(
    *,
    key_reference: str = ("test://verification-wrap/v1"),
) -> RSAOAEPKeyWrapper:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    return RSAOAEPKeyWrapper(
        public_key=private_key.public_key(),
        private_key=private_key,
        key_reference=key_reference,
        key_version=1,
        required_key_size=2048,
    )


def create_manifest() -> ForensicManifestArtifact:
    manifest = EvidenceForensicManifest(
        evidence_number=("EVD-VERIFY-DECRYPT"),
        incident_id=uuid4(),
        source_detection_id=None,
        source_type=(EvidenceSourceType.EXTERNAL_IMPORT),
        evidence_type=EvidenceType.IMAGE,
        original_filename="frame.jpg",
        mime_type="image/jpeg",
        file_size_bytes=len(_CONTENT),
        original_sha256=hashlib.sha256(_CONTENT).hexdigest(),
        captured_at=datetime(
            2026,
            8,
            13,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    return build_manifest_artifact(manifest)


def test_persisted_evidence_is_decrypted() -> None:
    key_wrapper = create_key_wrapper()
    manifest = create_manifest()

    secured = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    result = decrypt_persisted_evidence(
        encrypted_payload=(secured.encrypted_payload),
        encrypted_sha256=(secured.encrypted_sha256),
        wrapped_key_algorithm=(secured.wrapped_key.algorithm),
        wrapped_key_value=(secured.wrapped_key.wrapped_key),
        key_reference=(secured.wrapped_key.key_reference),
        key_version=(secured.wrapped_key.key_version),
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    assert isinstance(
        result,
        EvidenceDecryptionResult,
    )

    assert result.content == _CONTENT

    assert _CONTENT.decode() not in repr(result)


def test_wrong_private_key_fails_unwrap() -> None:
    original_wrapper = create_key_wrapper()

    wrong_wrapper = create_key_wrapper(key_reference=("test://verification-wrap/v1"))

    manifest = create_manifest()

    secured = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=original_wrapper,
    )

    with pytest.raises(EvidenceKeyUnwrapError):
        decrypt_persisted_evidence(
            encrypted_payload=(secured.encrypted_payload),
            encrypted_sha256=(secured.encrypted_sha256),
            wrapped_key_algorithm=(secured.wrapped_key.algorithm),
            wrapped_key_value=(secured.wrapped_key.wrapped_key),
            key_reference=(secured.wrapped_key.key_reference),
            key_version=(secured.wrapped_key.key_version),
            manifest=manifest,
            key_wrapper=wrong_wrapper,
        )


def test_tampered_ciphertext_fails_gcm_authentication() -> None:
    key_wrapper = create_key_wrapper()
    manifest = create_manifest()

    secured = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    tampered_payload = secured.encrypted_payload[:-1] + bytes(
        [secured.encrypted_payload[-1] ^ 0x01]
    )

    tampered_sha256 = hashlib.sha256(tampered_payload).hexdigest()

    with pytest.raises(EvidenceAuthenticationError):
        decrypt_persisted_evidence(
            encrypted_payload=(tampered_payload),
            encrypted_sha256=(tampered_sha256),
            wrapped_key_algorithm=(secured.wrapped_key.algorithm),
            wrapped_key_value=(secured.wrapped_key.wrapped_key),
            key_reference=(secured.wrapped_key.key_reference),
            key_version=(secured.wrapped_key.key_version),
            manifest=manifest,
            key_wrapper=key_wrapper,
        )


def test_wrong_manifest_fails_gcm_authentication() -> None:
    key_wrapper = create_key_wrapper()
    manifest = create_manifest()

    secured = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    wrong_manifest = EvidenceForensicManifest(
        evidence_number=("EVD-WRONG-MANIFEST"),
        incident_id=(manifest.manifest.incident_id),
        source_detection_id=None,
        source_type=(EvidenceSourceType.EXTERNAL_IMPORT),
        evidence_type=(EvidenceType.IMAGE),
        original_filename="frame.jpg",
        mime_type="image/jpeg",
        file_size_bytes=len(_CONTENT),
        original_sha256=(hashlib.sha256(_CONTENT).hexdigest()),
        captured_at=(manifest.manifest.captured_at),
    )

    wrong_artifact = build_manifest_artifact(wrong_manifest)

    with pytest.raises(EvidenceAuthenticationError):
        decrypt_persisted_evidence(
            encrypted_payload=(secured.encrypted_payload),
            encrypted_sha256=(secured.encrypted_sha256),
            wrapped_key_algorithm=(secured.wrapped_key.algorithm),
            wrapped_key_value=(secured.wrapped_key.wrapped_key),
            key_reference=(secured.wrapped_key.key_reference),
            key_version=(secured.wrapped_key.key_version),
            manifest=wrong_artifact,
            key_wrapper=key_wrapper,
        )


def test_wrong_key_reference_fails_unwrap() -> None:
    key_wrapper = create_key_wrapper()
    manifest = create_manifest()

    secured = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    with pytest.raises(EvidenceKeyUnwrapError):
        decrypt_persisted_evidence(
            encrypted_payload=(secured.encrypted_payload),
            encrypted_sha256=(secured.encrypted_sha256),
            wrapped_key_algorithm=(secured.wrapped_key.algorithm),
            wrapped_key_value=(secured.wrapped_key.wrapped_key),
            key_reference=("test://different-provider/v1"),
            key_version=(secured.wrapped_key.key_version),
            manifest=manifest,
            key_wrapper=key_wrapper,
        )
