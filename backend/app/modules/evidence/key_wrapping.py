from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import (
    padding,
    rsa,
)

from app.modules.evidence.errors import (
    EvidenceKeyUnwrapError,
    EvidenceKeyWrapError,
)

_DATA_ENCRYPTION_KEY_BYTES = 32
_DEFAULT_RSA_KEY_SIZE = 4096
_RSA_ALGORITHM = "RSA-OAEP-SHA256"

_OAEP_LABEL = b"secure-surveillance:evidence-dek:v1"


@dataclass(
    frozen=True,
    slots=True,
)
class WrappedEvidenceKey:
    algorithm: str
    wrapped_key: str
    key_reference: str
    key_version: int = 1

    def __post_init__(self) -> None:
        if not self.algorithm.strip():
            raise ValueError("algorithm must not be empty")

        if not self.wrapped_key.strip():
            raise ValueError("wrapped_key must not be empty")

        if not self.key_reference.strip():
            raise ValueError("key_reference must not be empty")

        if self.key_version <= 0:
            raise ValueError("key_version must be greater than zero")


@runtime_checkable
class EvidenceKeyWrapper(Protocol):
    """Abstraction for wrapping evidence DEKs."""

    def wrap_key(
        self,
        data_encryption_key: bytes,
    ) -> WrappedEvidenceKey:
        """Wrap a plaintext DEK."""

    def unwrap_key(
        self,
        wrapped_key: WrappedEvidenceKey,
    ) -> bytes:
        """Recover a DEK for authorized decryption."""


class RSAOAEPKeyWrapper:
    """RSA-OAEP/SHA-256 evidence-key wrapper."""

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
            raise ValueError(f"RSA wrapping key must be {required_key_size} bits")

        if private_key is not None:
            if private_key.key_size != required_key_size:
                raise ValueError(f"RSA private key must be {required_key_size} bits")

            if private_key.public_key().public_numbers() != public_key.public_numbers():
                raise ValueError("RSA public and private keys do not match")

        self._public_key = public_key
        self._private_key = private_key
        self._key_reference = key_reference.strip()
        self._key_version = key_version

    @property
    def key_reference(self) -> str:
        return self._key_reference

    @property
    def key_version(self) -> int:
        return self._key_version

    def wrap_key(
        self,
        data_encryption_key: bytes,
    ) -> WrappedEvidenceKey:
        if len(data_encryption_key) != _DATA_ENCRYPTION_KEY_BYTES:
            raise EvidenceKeyWrapError("Evidence DEK must contain exactly 32 bytes")

        try:
            ciphertext = self._public_key.encrypt(
                data_encryption_key,
                self._oaep_padding(),
            )
        except ValueError as exception:
            raise EvidenceKeyWrapError("Evidence DEK wrapping failed") from exception

        encoded = base64.b64encode(ciphertext).decode("ascii")

        return WrappedEvidenceKey(
            algorithm=_RSA_ALGORITHM,
            wrapped_key=encoded,
            key_reference=(self._key_reference),
            key_version=self._key_version,
        )

    def unwrap_key(
        self,
        wrapped_key: WrappedEvidenceKey,
    ) -> bytes:
        if self._private_key is None:
            raise EvidenceKeyUnwrapError("Private wrapping key is not available")

        if wrapped_key.algorithm != _RSA_ALGORITHM:
            raise EvidenceKeyUnwrapError("Unsupported key-wrapping algorithm")

        if wrapped_key.key_reference != self._key_reference:
            raise EvidenceKeyUnwrapError("Wrapped key reference does not match this provider")

        if wrapped_key.key_version != self._key_version:
            raise EvidenceKeyUnwrapError("Wrapped key version does not match this provider")

        try:
            ciphertext = base64.b64decode(
                wrapped_key.wrapped_key,
                validate=True,
            )
        except (
            binascii.Error,
            ValueError,
        ) as exception:
            raise EvidenceKeyUnwrapError("Wrapped evidence key is not valid Base64") from exception

        try:
            plaintext = self._private_key.decrypt(
                ciphertext,
                self._oaep_padding(),
            )
        except ValueError as exception:
            raise EvidenceKeyUnwrapError("Evidence DEK unwrapping failed") from exception

        if len(plaintext) != _DATA_ENCRYPTION_KEY_BYTES:
            raise EvidenceKeyUnwrapError("Recovered evidence DEK has an invalid length")

        return plaintext

    @staticmethod
    def _oaep_padding() -> padding.OAEP:
        return padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=_OAEP_LABEL,
        )
