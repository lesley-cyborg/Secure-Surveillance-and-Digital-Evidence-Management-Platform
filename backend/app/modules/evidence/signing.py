from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from cryptography.exceptions import (
    InvalidSignature,
)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import (
    padding,
    rsa,
)

from app.modules.evidence.errors import (
    EvidenceSignatureFormatError,
    EvidenceSigningError,
)

_SIGNATURE_ALGORITHM = "RSA-PSS-SHA256"
_SIGNATURE_SCHEMA_VERSION = "1.0"
_DEFAULT_RSA_KEY_SIZE = 4096

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _canonical_timestamp(
    value: datetime,
) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Signature timestamps must be timezone-aware")

    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_sha256(
    value: str,
    *,
    field_name: str,
) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


@dataclass(
    frozen=True,
    slots=True,
)
class DigitalSignatureEnvelope:
    algorithm: str
    key_reference: str
    key_version: int
    signature: str

    def __post_init__(self) -> None:
        if not self.algorithm.strip():
            raise ValueError("algorithm must not be empty")

        if not self.key_reference.strip():
            raise ValueError("key_reference must not be empty")

        if self.key_version <= 0:
            raise ValueError("key_version must be greater than zero")

        try:
            base64.b64decode(
                self.signature,
                validate=True,
            )
        except (
            binascii.Error,
            ValueError,
        ) as exception:
            raise ValueError("signature must contain valid Base64") from exception

    def to_json(self) -> str:
        return json.dumps(
            {
                "algorithm": self.algorithm,
                "key_reference": (self.key_reference),
                "key_version": self.key_version,
                "signature": self.signature,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(
        cls,
        value: str,
    ) -> DigitalSignatureEnvelope:
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exception:
            raise EvidenceSignatureFormatError("Digital signature is not valid JSON") from exception

        if not isinstance(raw, dict):
            raise EvidenceSignatureFormatError("Digital signature must be a JSON object")

        algorithm = raw.get("algorithm")
        key_reference = raw.get("key_reference")
        key_version = raw.get("key_version")
        signature = raw.get("signature")

        if not isinstance(algorithm, str):
            raise EvidenceSignatureFormatError("Signature algorithm is invalid")

        if not isinstance(
            key_reference,
            str,
        ):
            raise EvidenceSignatureFormatError("Signature key reference is invalid")

        if not isinstance(key_version, int) or isinstance(key_version, bool):
            raise EvidenceSignatureFormatError("Signature key version is invalid")

        if not isinstance(signature, str):
            raise EvidenceSignatureFormatError("Signature value is invalid")

        try:
            return cls(
                algorithm=algorithm,
                key_reference=key_reference,
                key_version=key_version,
                signature=signature,
            )
        except ValueError as exception:
            raise EvidenceSignatureFormatError(
                "Digital signature envelope is invalid"
            ) from exception


class ForensicSigner(Protocol):
    def sign(
        self,
        payload: bytes,
    ) -> DigitalSignatureEnvelope:
        """Digitally sign canonical bytes."""

    def verify(
        self,
        payload: bytes,
        signature: DigitalSignatureEnvelope,
    ) -> bool:
        """Verify canonical bytes."""


class RSAPSSSHA256Signer:
    """RSA-PSS/SHA-256 forensic signer."""

    def __init__(
        self,
        *,
        public_key: rsa.RSAPublicKey,
        key_reference: str,
        key_version: int = 1,
        private_key: (rsa.RSAPrivateKey | None) = None,
        required_key_size: int = (_DEFAULT_RSA_KEY_SIZE),
    ) -> None:
        if not key_reference.strip():
            raise ValueError("key_reference must not be empty")

        if key_version <= 0:
            raise ValueError("key_version must be greater than zero")

        if public_key.key_size != required_key_size:
            raise ValueError(f"RSA signing key must be {required_key_size} bits")

        if private_key is not None:
            if private_key.key_size != required_key_size:
                raise ValueError(f"RSA private signing key must be {required_key_size} bits")

            if private_key.public_key().public_numbers() != public_key.public_numbers():
                raise ValueError("RSA signing keys do not match")

        self._public_key = public_key
        self._private_key = private_key
        self._key_reference = key_reference.strip()
        self._key_version = key_version

    def sign(
        self,
        payload: bytes,
    ) -> DigitalSignatureEnvelope:
        if not payload:
            raise EvidenceSigningError("Cannot sign an empty payload")

        if self._private_key is None:
            raise EvidenceSigningError("Private signing key is unavailable")

        signature = self._private_key.sign(
            payload,
            self._padding(),
            hashes.SHA256(),
        )

        return DigitalSignatureEnvelope(
            algorithm=_SIGNATURE_ALGORITHM,
            key_reference=(self._key_reference),
            key_version=self._key_version,
            signature=(base64.b64encode(signature).decode("ascii")),
        )

    def verify(
        self,
        payload: bytes,
        signature: DigitalSignatureEnvelope,
    ) -> bool:
        if signature.algorithm != _SIGNATURE_ALGORITHM:
            return False

        if signature.key_reference != self._key_reference:
            return False

        if signature.key_version != self._key_version:
            return False

        try:
            signature_bytes = base64.b64decode(
                signature.signature,
                validate=True,
            )
        except (
            binascii.Error,
            ValueError,
        ):
            return False

        try:
            self._public_key.verify(
                signature_bytes,
                payload,
                self._padding(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            return False

        return True

    @staticmethod
    def _padding() -> padding.PSS:
        return padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=(padding.PSS.DIGEST_LENGTH),
        )


def build_evidence_signature_payload(
    *,
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
) -> bytes:
    """Create bytes signed for the Evidence row."""

    _require_sha256(
        original_sha256,
        field_name="original_sha256",
    )
    _require_sha256(
        encrypted_sha256,
        field_name="encrypted_sha256",
    )
    _require_sha256(
        manifest_sha256,
        field_name="manifest_sha256",
    )

    payload = {
        "schema_version": (_SIGNATURE_SCHEMA_VERSION),
        "evidence_number": evidence_number,
        "incident_id": str(incident_id),
        "source_detection_id": (
            str(source_detection_id) if source_detection_id is not None else None
        ),
        "storage_bucket": storage_bucket,
        "storage_object_key": (storage_object_key),
        "storage_version_id": (storage_version_id),
        "original_sha256": (original_sha256),
        "encrypted_sha256": (encrypted_sha256),
        "manifest_sha256": (manifest_sha256),
        "captured_at": (_canonical_timestamp(captured_at)),
        "ingested_at": (_canonical_timestamp(ingested_at)),
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
