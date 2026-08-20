from __future__ import annotations

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import (
    AESGCM,
)

from app.modules.evidence.errors import (
    EvidenceAuthenticationError,
    EvidenceEnvelopeError,
    EvidenceEnvelopeIntegrityError,
    EvidenceManifestMismatchError,
)
from app.modules.evidence.forensics import (
    ForensicManifestArtifact,
)
from app.modules.evidence.key_wrapping import (
    EvidenceKeyWrapper,
    WrappedEvidenceKey,
)

_AES_KEY_BITS = 256
_AES_KEY_BYTES = 32
_GCM_NONCE_BYTES = 12
_GCM_TAG_BYTES = 16

_ENVELOPE_MAGIC = b"SSPE"
_ENVELOPE_VERSION = 1

_HEADER = struct.Struct("!4sBB")

_ENCRYPTION_ALGORITHM = "AES-256-GCM"


@dataclass(
    frozen=True,
    slots=True,
)
class SecuredEvidenceArtifact:
    """Encrypted evidence ready for object storage."""

    encrypted_payload: bytes = field(repr=False)

    encrypted_sha256: str

    wrapped_key: WrappedEvidenceKey

    algorithm: str = _ENCRYPTION_ALGORITHM

    envelope_version: int = _ENVELOPE_VERSION

    def __post_init__(self) -> None:
        if not self.encrypted_payload:
            raise ValueError("encrypted_payload must not be empty")

        if len(self.encrypted_sha256) != 64:
            raise ValueError("encrypted_sha256 must contain 64 characters")

        try:
            bytes.fromhex(self.encrypted_sha256)
        except ValueError as exception:
            raise ValueError("encrypted_sha256 must be valid hexadecimal") from exception

        if self.encrypted_sha256 != self.encrypted_sha256.lower():
            raise ValueError("encrypted_sha256 must use lowercase hexadecimal")

        if self.algorithm != _ENCRYPTION_ALGORITHM:
            raise ValueError("Unsupported evidence encryption algorithm")

        if self.envelope_version != _ENVELOPE_VERSION:
            raise ValueError("Unsupported evidence envelope version")


def secure_evidence(
    content: bytes,
    *,
    manifest: ForensicManifestArtifact,
    key_wrapper: EvidenceKeyWrapper,
) -> SecuredEvidenceArtifact:
    """Encrypt and wrap one forensic evidence object.

    The plaintext DEK exists only inside this function.
    It is never returned as part of the artifact.
    """

    _validate_original_content(
        content,
        manifest=manifest,
    )

    data_encryption_key = AESGCM.generate_key(bit_length=_AES_KEY_BITS)

    if len(data_encryption_key) != _AES_KEY_BYTES:
        raise RuntimeError("Generated AES-256 key has an unexpected length")

    nonce = os.urandom(_GCM_NONCE_BYTES)

    aesgcm = AESGCM(data_encryption_key)

    ciphertext_and_tag = aesgcm.encrypt(
        nonce,
        content,
        manifest.canonical_bytes,
    )

    envelope = _build_envelope(
        nonce=nonce,
        ciphertext_and_tag=(ciphertext_and_tag),
    )

    wrapped_key = key_wrapper.wrap_key(data_encryption_key)

    encrypted_sha256 = hashlib.sha256(envelope).hexdigest()

    return SecuredEvidenceArtifact(
        encrypted_payload=envelope,
        encrypted_sha256=(encrypted_sha256),
        wrapped_key=wrapped_key,
    )


def decrypt_evidence(
    artifact: SecuredEvidenceArtifact,
    *,
    manifest: ForensicManifestArtifact,
    key_wrapper: EvidenceKeyWrapper,
) -> bytes:
    """Verify, unwrap and decrypt one evidence artifact."""

    calculated_encrypted_sha256 = hashlib.sha256(artifact.encrypted_payload).hexdigest()

    if not hmac.compare_digest(
        calculated_encrypted_sha256,
        artifact.encrypted_sha256,
    ):
        raise EvidenceEnvelopeIntegrityError("Encrypted evidence SHA-256 does not match")

    nonce, ciphertext_and_tag = _parse_envelope(artifact.encrypted_payload)

    data_encryption_key = key_wrapper.unwrap_key(artifact.wrapped_key)

    if len(data_encryption_key) != _AES_KEY_BYTES:
        raise EvidenceAuthenticationError("Recovered evidence DEK has an invalid length")

    try:
        plaintext = AESGCM(data_encryption_key).decrypt(
            nonce,
            ciphertext_and_tag,
            manifest.canonical_bytes,
        )
    except InvalidTag as exception:
        raise EvidenceAuthenticationError("Encrypted evidence authentication failed") from exception

    _validate_original_content(
        plaintext,
        manifest=manifest,
    )

    return plaintext


def _validate_original_content(
    content: bytes,
    *,
    manifest: ForensicManifestArtifact,
) -> None:
    if not content:
        raise EvidenceManifestMismatchError("Evidence content must not be empty")

    expected_size = manifest.manifest.file_size_bytes

    if len(content) != expected_size:
        raise EvidenceManifestMismatchError("Evidence size does not match forensic manifest")

    calculated_sha256 = hashlib.sha256(content).hexdigest()

    if not hmac.compare_digest(
        calculated_sha256,
        manifest.manifest.original_sha256,
    ):
        raise EvidenceManifestMismatchError("Evidence SHA-256 does not match forensic manifest")

    calculated_manifest_sha256 = hashlib.sha256(manifest.canonical_bytes).hexdigest()

    if not hmac.compare_digest(
        calculated_manifest_sha256,
        manifest.sha256,
    ):
        raise EvidenceManifestMismatchError("Canonical manifest digest does not match artifact")


def _build_envelope(
    *,
    nonce: bytes,
    ciphertext_and_tag: bytes,
) -> bytes:
    if len(nonce) != _GCM_NONCE_BYTES:
        raise EvidenceEnvelopeError("AES-GCM nonce must contain 12 bytes")

    if len(ciphertext_and_tag) <= _GCM_TAG_BYTES:
        raise EvidenceEnvelopeError("Encrypted evidence payload is too short")

    header = _HEADER.pack(
        _ENVELOPE_MAGIC,
        _ENVELOPE_VERSION,
        len(nonce),
    )

    return header + nonce + ciphertext_and_tag


def _parse_envelope(
    payload: bytes,
) -> tuple[bytes, bytes]:
    minimum_length = _HEADER.size + _GCM_NONCE_BYTES + _GCM_TAG_BYTES + 1

    if len(payload) < minimum_length:
        raise EvidenceEnvelopeError("Encrypted evidence envelope is truncated")

    try:
        (
            magic,
            version,
            nonce_length,
        ) = _HEADER.unpack_from(payload)
    except struct.error as exception:
        raise EvidenceEnvelopeError("Encrypted evidence envelope header is invalid") from exception

    if magic != _ENVELOPE_MAGIC:
        raise EvidenceEnvelopeError("Encrypted evidence envelope magic is invalid")

    if version != _ENVELOPE_VERSION:
        raise EvidenceEnvelopeError("Unsupported encrypted evidence envelope version")

    if nonce_length != _GCM_NONCE_BYTES:
        raise EvidenceEnvelopeError("Encrypted evidence nonce length is invalid")

    nonce_start = _HEADER.size
    nonce_end = nonce_start + nonce_length

    nonce = payload[nonce_start:nonce_end]

    ciphertext_and_tag = payload[nonce_end:]

    if len(ciphertext_and_tag) <= _GCM_TAG_BYTES:
        raise EvidenceEnvelopeError("Encrypted evidence ciphertext is truncated")

    return (
        nonce,
        ciphertext_and_tag,
    )
