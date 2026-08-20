from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.core.config import get_settings
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
    EvidenceObjectNotFoundError,
)
from app.modules.evidence.forensics import (
    EvidenceForensicManifest,
    ForensicManifestArtifact,
    build_manifest_artifact,
)
from app.modules.evidence.identifiers import (
    generate_evidence_number,
)
from app.modules.evidence.key_wrapping import (
    RSAOAEPKeyWrapper,
)
from app.modules.evidence.minio_storage import (
    MinioEvidenceObjectStorage,
)
from app.modules.evidence.storage import (
    build_evidence_object_key,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)

_CONTENT = b"secure-surveillance-minio-integration-evidence"


@pytest.fixture(scope="module")
def key_wrapper() -> RSAOAEPKeyWrapper:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    return RSAOAEPKeyWrapper(
        public_key=(private_key.public_key()),
        private_key=private_key,
        key_reference=("test://minio-evidence-rsa/v1"),
        key_version=1,
    )


async def create_storage() -> MinioEvidenceObjectStorage:
    storage = MinioEvidenceObjectStorage.from_settings(get_settings())

    await storage.ensure_ready()

    return storage


def create_manifest(
    *,
    content: bytes = _CONTENT,
) -> ForensicManifestArtifact:
    captured_at = datetime.now(UTC)

    evidence_number = generate_evidence_number(captured_at=captured_at)

    manifest = EvidenceForensicManifest(
        evidence_number=evidence_number,
        incident_id=uuid4(),
        source_detection_id=uuid4(),
        source_type=(EvidenceSourceType.AI_CAPTURE),
        evidence_type=EvidenceType.IMAGE,
        original_filename=("minio-integration-frame.jpg"),
        mime_type="image/jpeg",
        file_size_bytes=len(content),
        original_sha256=(hashlib.sha256(content).hexdigest()),
        captured_at=captured_at,
    )

    return build_manifest_artifact(manifest)


@pytest.mark.asyncio
async def test_encrypted_evidence_round_trip_through_minio(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    storage = await create_storage()

    manifest = create_manifest()

    artifact = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    object_key = build_evidence_object_key(
        incident_id=(manifest.manifest.incident_id),
        evidence_number=(manifest.manifest.evidence_number),
        captured_at=(manifest.manifest.captured_at),
        encrypted_sha256=(artifact.encrypted_sha256),
    )

    stored = None

    try:
        stored = await storage.put_object(
            object_key=object_key,
            payload=(artifact.encrypted_payload),
            content_type=("application/octet-stream"),
            metadata={
                "Evidence-Number": (manifest.manifest.evidence_number),
                "Incident-ID": str(manifest.manifest.incident_id),
                "Encrypted-SHA256": (artifact.encrypted_sha256),
                "Manifest-SHA256": (manifest.sha256),
                "Envelope-Version": str(artifact.envelope_version),
            },
        )

        assert stored.size_bytes == len(artifact.encrypted_payload)

        assert stored.version_id is not None

        downloaded = await storage.get_object(
            object_key=object_key,
            version_id=(stored.version_id),
        )

        assert downloaded == artifact.encrypted_payload

        assert hashlib.sha256(downloaded).hexdigest() == artifact.encrypted_sha256

        restored_artifact = SecuredEvidenceArtifact(
            encrypted_payload=downloaded,
            encrypted_sha256=(artifact.encrypted_sha256),
            wrapped_key=(artifact.wrapped_key),
        )

        plaintext = decrypt_evidence(
            restored_artifact,
            manifest=manifest,
            key_wrapper=key_wrapper,
        )

        assert plaintext == _CONTENT

    finally:
        if stored is not None:
            await storage.delete_for_compensation(
                object_key=object_key,
                version_id=(stored.version_id),
            )


@pytest.mark.asyncio
async def test_minio_preserves_distinct_object_versions(
    key_wrapper: RSAOAEPKeyWrapper,
) -> None:
    storage = await create_storage()

    manifest = create_manifest()

    first_artifact = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    second_artifact = secure_evidence(
        _CONTENT,
        manifest=manifest,
        key_wrapper=key_wrapper,
    )

    object_key = f"integration/versioning/{uuid4().hex}.sspe"

    first = None
    second = None

    try:
        first = await storage.put_object(
            object_key=object_key,
            payload=(first_artifact.encrypted_payload),
            content_type=("application/octet-stream"),
        )

        second = await storage.put_object(
            object_key=object_key,
            payload=(second_artifact.encrypted_payload),
            content_type=("application/octet-stream"),
        )

        assert first.version_id is not None
        assert second.version_id is not None

        assert first.version_id != second.version_id

        first_download = await storage.get_object(
            object_key=object_key,
            version_id=(first.version_id),
        )

        second_download = await storage.get_object(
            object_key=object_key,
            version_id=(second.version_id),
        )

        assert first_download == first_artifact.encrypted_payload

        assert second_download == second_artifact.encrypted_payload

    finally:
        if second is not None:
            await storage.delete_for_compensation(
                object_key=object_key,
                version_id=(second.version_id),
            )

        if first is not None:
            await storage.delete_for_compensation(
                object_key=object_key,
                version_id=(first.version_id),
            )


@pytest.mark.asyncio
async def test_missing_minio_object_is_mapped_to_domain_error() -> None:
    storage = await create_storage()

    object_key = f"integration/missing/{uuid4().hex}.sspe"

    with pytest.raises(EvidenceObjectNotFoundError):
        await storage.get_object(object_key=object_key)
