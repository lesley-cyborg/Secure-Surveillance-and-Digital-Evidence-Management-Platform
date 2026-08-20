from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import app.modules.evidence.verification_orchestrator as orchestrator_module
import pytest
from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceType,
    VerificationStatus,
)
from app.modules.evidence.errors import (
    EvidenceAuthenticationError,
    EvidenceObjectNotFoundError,
    EvidenceStorageUnavailableError,
)
from app.modules.evidence.key_wrapping import (
    EvidenceKeyWrapper,
)
from app.modules.evidence.signing import (
    ForensicSigner,
)
from app.modules.evidence.storage import (
    EvidenceObjectStorage,
    StoredEvidenceObject,
)
from app.modules.evidence.verification import (
    EvidenceContentVerificationResult,
    EvidenceDecryptionResult,
    EvidenceSignatureVerificationResult,
    EvidenceVerificationCommand,
    EvidenceVerificationResult,
)
from app.modules.evidence.verification_orchestrator import (
    EvidenceVerificationOrchestrator,
    PersistedEvidenceKeyMaterial,
    PersistedEvidenceVerificationMaterial,
)
from app.modules.evidence.verification_service import (
    EvidenceVerificationPersistenceService,
)
from sqlalchemy.ext.asyncio import AsyncSession

_ENCRYPTED_PAYLOAD = b"secure-surveillance-verification-encrypted-object"

_ORIGINAL_SHA256 = hashlib.sha256(b"secure-surveillance-original-evidence").hexdigest()

_ENCRYPTED_SHA256 = hashlib.sha256(_ENCRYPTED_PAYLOAD).hexdigest()

_MANIFEST_SHA256 = "3" * 64

_STORAGE_BUCKET = "evidence"

_STORAGE_OBJECT_KEY = (
    f"incidents/verification-test/2026/08/14/EVD-VERIFY-TEST/{_ENCRYPTED_SHA256}.sspe"
)

_STORAGE_VERSION_ID = "verification-test-version-1"


class StubStorage:
    """Minimal object-storage probe for orchestration tests."""

    def __init__(
        self,
        *,
        payload: bytes = _ENCRYPTED_PAYLOAD,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.error = error

        self.get_count = 0
        self.last_object_key: str | None = None
        self.last_version_id: str | None = None

    async def ensure_ready(
        self,
    ) -> None:
        return None

    async def put_object(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> StoredEvidenceObject:
        del (
            object_key,
            payload,
            content_type,
            metadata,
        )

        raise AssertionError("Verification must not upload evidence")

    async def get_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> bytes:
        self.get_count += 1
        self.last_object_key = object_key
        self.last_version_id = version_id

        if self.error is not None:
            raise self.error

        return self.payload

    async def stat_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> StoredEvidenceObject:
        del (
            object_key,
            version_id,
        )

        raise AssertionError(
            "Verification orchestration must not require a separate object-stat operation"
        )

    async def delete_for_compensation(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> None:
        del (
            object_key,
            version_id,
        )

        raise AssertionError("Verification must never perform ingestion compensation")


class StubVerificationPersistence:
    """
    Capture verification outcomes without PostgreSQL.

    Persistence transaction behaviour is already covered separately by
    the 6.2I.7 and 6.2I.8 integration tests.
    """

    def __init__(self) -> None:
        self.record_count = 0

        self.last_command: EvidenceVerificationCommand | None = None

        self.last_status: VerificationStatus | None = None

        self.last_expected_sha256: str | None = None

        self.last_calculated_sha256: str | None = None

        self.last_hash_matches: bool | None = None
        self.last_signature_valid: bool | None = None
        self.last_failure_reason: str | None = None

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
        self.record_count += 1

        self.last_command = command
        self.last_status = verification_status

        self.last_expected_sha256 = expected_sha256

        self.last_calculated_sha256 = calculated_sha256

        self.last_hash_matches = hash_matches

        self.last_signature_valid = signature_valid

        self.last_failure_reason = failure_reason

        return EvidenceVerificationResult(
            evidence_id=command.evidence_id,
            verification_id=uuid4(),
            verification_status=(verification_status),
            expected_sha256=expected_sha256,
            calculated_sha256=(calculated_sha256),
            hash_matches=hash_matches,
            signature_valid=signature_valid,
            verified_at=verified_at,
            failure_reason=failure_reason,
            custody_record_id=None,
            audit_log_id=uuid4(),
        )


def create_evidence_material(
    *,
    evidence_id: UUID | None = None,
    encrypted_sha256: str = _ENCRYPTED_SHA256,
) -> PersistedEvidenceVerificationMaterial:
    captured_at = datetime(
        2026,
        8,
        14,
        12,
        30,
        tzinfo=UTC,
    )

    ingested_at = datetime(
        2026,
        8,
        14,
        12,
        31,
        tzinfo=UTC,
    )

    return PersistedEvidenceVerificationMaterial(
        evidence_id=evidence_id or uuid4(),
        evidence_number="EVD-VERIFY-TEST",
        incident_id=uuid4(),
        source_detection_id=None,
        source_type=(EvidenceSourceType.EXTERNAL_IMPORT),
        evidence_type=EvidenceType.IMAGE,
        original_filename="verification-test.jpg",
        mime_type="image/jpeg",
        file_size_bytes=(len(b"secure-surveillance-original-evidence")),
        storage_bucket=_STORAGE_BUCKET,
        storage_object_key=_STORAGE_OBJECT_KEY,
        storage_version_id=_STORAGE_VERSION_ID,
        original_sha256=_ORIGINAL_SHA256,
        encrypted_sha256=encrypted_sha256,
        manifest_sha256=_MANIFEST_SHA256,
        digital_signature=(
            '{"algorithm":"RSA-PSS-SHA256",'
            '"key_reference":"test://signing/v1",'
            '"key_version":1,'
            '"signature":"dGVzdA=="}'
        ),
        captured_at=captured_at,
        ingested_at=ingested_at,
    )


def create_key_material() -> PersistedEvidenceKeyMaterial:
    return PersistedEvidenceKeyMaterial(
        algorithm="RSA-OAEP-SHA256",
        wrapped_key="dGVzdC13cmFwcGVkLWtleQ==",
        key_reference="test://wrapping/v1",
        key_version=1,
    )


def create_command(
    *,
    evidence_id: UUID,
) -> EvidenceVerificationCommand:
    return EvidenceVerificationCommand(
        evidence_id=evidence_id,
        verified_by_user_id=None,
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent="pytest/evidence-verification",
        device_identifier="pytest-unit",
    )


def create_orchestrator(
    *,
    storage: StubStorage,
) -> tuple[
    EvidenceVerificationOrchestrator,
    StubVerificationPersistence,
]:
    session = cast(
        AsyncSession,
        object(),
    )

    key_wrapper = cast(
        EvidenceKeyWrapper,
        object(),
    )

    signer = cast(
        ForensicSigner,
        object(),
    )

    orchestrator = EvidenceVerificationOrchestrator(
        session=session,
        storage=cast(
            EvidenceObjectStorage,
            storage,
        ),
        key_wrapper=key_wrapper,
        signer=signer,
    )

    persistence = StubVerificationPersistence()

    orchestrator.persistence = cast(
        EvidenceVerificationPersistenceService,
        persistence,
    )

    return (
        orchestrator,
        persistence,
    )


def install_material_loader(
    monkeypatch: pytest.MonkeyPatch,
    *,
    evidence: PersistedEvidenceVerificationMaterial,
    key: PersistedEvidenceKeyMaterial | None,
) -> None:
    async def load_material(
        self: EvidenceVerificationOrchestrator,
        *,
        evidence_id: UUID,
    ) -> tuple[
        PersistedEvidenceVerificationMaterial,
        PersistedEvidenceKeyMaterial | None,
    ]:
        del self

        assert evidence_id == evidence.evidence_id

        return (
            evidence,
            key,
        )

    monkeypatch.setattr(
        EvidenceVerificationOrchestrator,
        "_load_material",
        load_material,
    )


def fail_if_signature_verification_reached(
    **_kwargs: object,
) -> EvidenceSignatureVerificationResult:
    raise AssertionError("Signature verification must not be reached")


def fail_if_decryption_reached(
    **_kwargs: object,
) -> EvidenceDecryptionResult:
    raise AssertionError("Evidence decryption must not be reached")


def fail_if_content_verification_reached(
    **_kwargs: object,
) -> EvidenceContentVerificationResult:
    raise AssertionError("Plaintext verification must not be reached")


def successful_signature_verification(
    **_kwargs: object,
) -> EvidenceSignatureVerificationResult:
    return EvidenceSignatureVerificationResult(
        signature_valid=True,
        signature_format_valid=True,
        failure_reason=None,
    )


@pytest.mark.asyncio
async def test_missing_object_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = create_evidence_material()
    key = create_key_material()

    storage = StubStorage(error=EvidenceObjectNotFoundError("Evidence object is missing"))

    orchestrator, persistence = create_orchestrator(
        storage=storage,
    )

    install_material_loader(
        monkeypatch,
        evidence=evidence,
        key=key,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_signature",
        fail_if_signature_verification_reached,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "decrypt_persisted_evidence",
        fail_if_decryption_reached,
    )

    command = create_command(evidence_id=evidence.evidence_id)

    result = await orchestrator.verify(
        command=command,
    )

    assert result.verification_status is (VerificationStatus.UNAVAILABLE)
    assert result.hash_matches is False
    assert result.signature_valid is False
    assert result.custody_record_id is None

    assert result.calculated_sha256 is None

    assert result.expected_sha256 == evidence.encrypted_sha256

    assert storage.get_count == 1

    assert storage.last_object_key == evidence.storage_object_key

    assert storage.last_version_id == evidence.storage_version_id

    assert persistence.record_count == 1

    assert persistence.last_status is (VerificationStatus.UNAVAILABLE)

    assert persistence.last_hash_matches is False

    assert persistence.last_signature_valid is False


@pytest.mark.asyncio
async def test_storage_outage_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = create_evidence_material()
    key = create_key_material()

    storage = StubStorage(error=EvidenceStorageUnavailableError("MinIO transport unavailable"))

    orchestrator, persistence = create_orchestrator(
        storage=storage,
    )

    install_material_loader(
        monkeypatch,
        evidence=evidence,
        key=key,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_signature",
        fail_if_signature_verification_reached,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "decrypt_persisted_evidence",
        fail_if_decryption_reached,
    )

    result = await orchestrator.verify(command=create_command(evidence_id=evidence.evidence_id))

    assert result.verification_status is (VerificationStatus.UNAVAILABLE)
    assert result.hash_matches is False
    assert result.signature_valid is False
    assert result.custody_record_id is None

    assert result.calculated_sha256 is None

    assert storage.get_count == 1

    assert persistence.record_count == 1

    assert persistence.last_status is (VerificationStatus.UNAVAILABLE)


@pytest.mark.asyncio
async def test_missing_active_key_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = create_evidence_material()

    storage = StubStorage()

    orchestrator, persistence = create_orchestrator(
        storage=storage,
    )

    install_material_loader(
        monkeypatch,
        evidence=evidence,
        key=None,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_signature",
        fail_if_signature_verification_reached,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "decrypt_persisted_evidence",
        fail_if_decryption_reached,
    )

    result = await orchestrator.verify(command=create_command(evidence_id=evidence.evidence_id))

    assert result.verification_status is (VerificationStatus.UNAVAILABLE)
    assert result.hash_matches is False
    assert result.signature_valid is False
    assert result.custody_record_id is None

    assert result.calculated_sha256 is None

    # The orchestrator should detect the missing key
    # before making a MinIO request.
    assert storage.get_count == 0

    assert persistence.record_count == 1

    assert persistence.last_status is (VerificationStatus.UNAVAILABLE)


@pytest.mark.asyncio
async def test_encrypted_digest_mismatch_is_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_payload = b"expected-encrypted-object"

    expected_sha256 = hashlib.sha256(expected_payload).hexdigest()

    evidence = create_evidence_material(
        encrypted_sha256=expected_sha256,
    )

    key = create_key_material()

    tampered_payload = b"tampered-encrypted-object"

    storage = StubStorage(
        payload=tampered_payload,
    )

    orchestrator, persistence = create_orchestrator(
        storage=storage,
    )

    install_material_loader(
        monkeypatch,
        evidence=evidence,
        key=key,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_signature",
        fail_if_signature_verification_reached,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "decrypt_persisted_evidence",
        fail_if_decryption_reached,
    )

    result = await orchestrator.verify(command=create_command(evidence_id=evidence.evidence_id))

    expected_calculated_sha256 = hashlib.sha256(tampered_payload).hexdigest()

    assert result.verification_status is (VerificationStatus.HASH_MISMATCH)
    assert result.hash_matches is False

    # Signature verification was deliberately
    # short-circuited by the encrypted digest failure.
    assert result.signature_valid is False

    assert result.custody_record_id is None

    assert result.expected_sha256 == expected_sha256

    assert result.calculated_sha256 == expected_calculated_sha256

    assert persistence.record_count == 1

    assert persistence.last_status is (VerificationStatus.HASH_MISMATCH)

    assert persistence.last_hash_matches is False

    assert persistence.last_signature_valid is False


@pytest.mark.asyncio
async def test_invalid_signature_is_signature_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = create_evidence_material()
    key = create_key_material()

    storage = StubStorage(
        payload=_ENCRYPTED_PAYLOAD,
    )

    orchestrator, persistence = create_orchestrator(
        storage=storage,
    )

    install_material_loader(
        monkeypatch,
        evidence=evidence,
        key=key,
    )

    def invalid_signature(
        **_kwargs: object,
    ) -> EvidenceSignatureVerificationResult:
        return EvidenceSignatureVerificationResult(
            signature_valid=False,
            signature_format_valid=True,
            failure_reason=("Stored digital signature did not verify"),
        )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_signature",
        invalid_signature,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "decrypt_persisted_evidence",
        fail_if_decryption_reached,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_content",
        fail_if_content_verification_reached,
    )

    result = await orchestrator.verify(command=create_command(evidence_id=evidence.evidence_id))

    assert result.verification_status is (VerificationStatus.SIGNATURE_INVALID)

    # The encrypted object itself matched its
    # persisted digest before the signature failed.
    assert result.hash_matches is True

    assert result.signature_valid is False
    assert result.custody_record_id is None

    assert result.calculated_sha256 == evidence.encrypted_sha256

    assert persistence.record_count == 1

    assert persistence.last_status is (VerificationStatus.SIGNATURE_INVALID)

    assert persistence.last_hash_matches is True

    assert persistence.last_signature_valid is False


@pytest.mark.asyncio
async def test_aes_authentication_failure_is_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = create_evidence_material()
    key = create_key_material()

    storage = StubStorage(
        payload=_ENCRYPTED_PAYLOAD,
    )

    orchestrator, persistence = create_orchestrator(
        storage=storage,
    )

    install_material_loader(
        monkeypatch,
        evidence=evidence,
        key=key,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_signature",
        successful_signature_verification,
    )

    def fail_authentication(
        **_kwargs: object,
    ) -> EvidenceDecryptionResult:
        raise EvidenceAuthenticationError("Encrypted evidence authentication failed")

    monkeypatch.setattr(
        orchestrator_module,
        "decrypt_persisted_evidence",
        fail_authentication,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_content",
        fail_if_content_verification_reached,
    )

    result = await orchestrator.verify(command=create_command(evidence_id=evidence.evidence_id))

    assert result.verification_status is (VerificationStatus.HASH_MISMATCH)

    assert result.hash_matches is False

    # Signature verification succeeded before
    # AES-GCM authentication failed.
    assert result.signature_valid is True

    assert result.custody_record_id is None

    assert result.calculated_sha256 == evidence.encrypted_sha256

    assert persistence.record_count == 1

    assert persistence.last_status is (VerificationStatus.HASH_MISMATCH)

    assert persistence.last_hash_matches is False

    assert persistence.last_signature_valid is True


@pytest.mark.asyncio
async def test_plaintext_or_manifest_mismatch_is_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = create_evidence_material()
    key = create_key_material()

    storage = StubStorage(
        payload=_ENCRYPTED_PAYLOAD,
    )

    orchestrator, persistence = create_orchestrator(
        storage=storage,
    )

    install_material_loader(
        monkeypatch,
        evidence=evidence,
        key=key,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_signature",
        successful_signature_verification,
    )

    plaintext = b"secure-surveillance-original-evidence"

    def successful_decryption(
        **_kwargs: object,
    ) -> EvidenceDecryptionResult:
        return EvidenceDecryptionResult(
            content=plaintext,
        )

    monkeypatch.setattr(
        orchestrator_module,
        "decrypt_persisted_evidence",
        successful_decryption,
    )

    calculated_original_sha256 = hashlib.sha256(plaintext).hexdigest()

    mismatched_manifest_sha256 = "4" * 64

    def mismatched_content(
        **_kwargs: object,
    ) -> EvidenceContentVerificationResult:
        return EvidenceContentVerificationResult(
            expected_original_sha256=(evidence.original_sha256),
            calculated_original_sha256=(calculated_original_sha256),
            expected_manifest_sha256=(evidence.manifest_sha256),
            calculated_manifest_sha256=(mismatched_manifest_sha256),
            original_hash_matches=True,
            manifest_hash_matches=False,
        )

    monkeypatch.setattr(
        orchestrator_module,
        "verify_evidence_content",
        mismatched_content,
    )

    result = await orchestrator.verify(command=create_command(evidence_id=evidence.evidence_id))

    assert result.verification_status is (VerificationStatus.HASH_MISMATCH)

    assert result.hash_matches is False

    # Signature verification has already succeeded.
    assert result.signature_valid is True

    assert result.custody_record_id is None

    assert result.calculated_sha256 == evidence.encrypted_sha256

    assert persistence.record_count == 1

    assert persistence.last_status is (VerificationStatus.HASH_MISMATCH)

    assert persistence.last_hash_matches is False

    assert persistence.last_signature_valid is True
