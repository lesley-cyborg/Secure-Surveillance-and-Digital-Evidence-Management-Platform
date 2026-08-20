from __future__ import annotations


class EvidenceCryptographyError(Exception):
    """Base exception for evidence cryptography failures."""


class EvidenceManifestMismatchError(EvidenceCryptographyError):
    """Evidence bytes do not match the forensic manifest."""


class EvidenceEnvelopeError(EvidenceCryptographyError):
    """Encrypted evidence envelope is malformed."""


class EvidenceEnvelopeIntegrityError(EvidenceCryptographyError):
    """Encrypted evidence does not match its recorded digest."""


class EvidenceAuthenticationError(EvidenceCryptographyError):
    """AES-GCM authentication failed."""


class EvidenceKeyWrapError(EvidenceCryptographyError):
    """Data-encryption key wrapping failed."""


class EvidenceKeyUnwrapError(EvidenceCryptographyError):
    """Wrapped data-encryption key could not be recovered."""


class EvidenceStorageError(Exception):
    """Base exception for evidence object-storage failures."""


class EvidenceStorageConfigurationError(EvidenceStorageError):
    """Evidence storage is incorrectly configured."""


class EvidenceStorageUnavailableError(EvidenceStorageError):
    """Evidence object storage is temporarily unavailable."""


class EvidenceObjectNotFoundError(EvidenceStorageError):
    """Requested evidence object does not exist."""


class EvidenceStorageIntegrityError(EvidenceStorageError):
    """Stored object metadata does not match the uploaded artifact."""


class EvidenceSigningError(Exception):
    """Evidence or custody digital signing failed."""


class EvidenceSignatureFormatError(EvidenceSigningError):
    """A stored digital-signature envelope is invalid."""


class EvidenceIngestionError(Exception):
    """Base exception for secure evidence ingestion."""


class EvidenceReferenceError(EvidenceIngestionError):
    """Incident or source-detection references are invalid."""


class EvidenceIngestionCompensationError(EvidenceIngestionError):
    """Cleanup failed after an evidence-ingestion failure."""


class EvidenceVerificationError(Exception):
    """Base exception for evidence-verification orchestration failures."""


class EvidenceVerificationReferenceError(EvidenceVerificationError):
    """Evidence requested for verification does not exist."""


class EvidenceRetrievalError(Exception):
    """Evidence plaintext retrieval failed."""


class EvidenceRetrievalUnavailableError(EvidenceRetrievalError):
    """Evidence cannot currently be retrieved."""


class EvidenceRetrievalHashMismatchError(EvidenceRetrievalError):
    """Evidence failed forensic integrity verification."""


class EvidenceRetrievalSignatureInvalidError(EvidenceRetrievalError):
    """Evidence failed authenticity verification."""
