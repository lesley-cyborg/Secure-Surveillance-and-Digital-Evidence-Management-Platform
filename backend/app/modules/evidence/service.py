from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
)
from app.db.models.incidents import Incident
from app.db.models.surveillance import (
    DetectionEvent,
)
from app.modules.audit.actions import (
    AuditAction,
)
from app.modules.audit.repository import (
    AuditRepository,
)
from app.modules.custody.integrity import (
    build_custody_integrity,
)
from app.modules.custody.repository import (
    CustodyRepository,
)
from app.modules.evidence.contracts import (
    PreparedEvidenceKey,
    PreparedEvidenceRecord,
)
from app.modules.evidence.crypto import (
    secure_evidence,
)
from app.modules.evidence.errors import (
    EvidenceIngestionCompensationError,
    EvidenceObjectNotFoundError,
    EvidenceReferenceError,
)
from app.modules.evidence.forensics import (
    EvidenceForensicManifest,
    analyze_evidence_bytes,
    build_manifest_artifact,
)
from app.modules.evidence.identifiers import (
    generate_evidence_number,
)
from app.modules.evidence.key_wrapping import (
    EvidenceKeyWrapper,
)
from app.modules.evidence.repository import (
    EvidenceRepository,
)
from app.modules.evidence.signing import (
    ForensicSigner,
    build_evidence_signature_payload,
)
from app.modules.evidence.storage import (
    EvidenceObjectStorage,
    StoredEvidenceObject,
    build_evidence_object_key,
)


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceIngestionCommand:
    incident_id: UUID
    source_detection_id: UUID | None

    submitted_by_user_id: UUID | None

    source_type: EvidenceSourceType
    evidence_type: EvidenceType

    original_filename: str
    mime_type: str

    captured_at: datetime

    content: bytes = field(repr=False)

    correlation_id: str

    source_artifact_id: UUID | None = None

    source_ip: str | None = None
    user_agent: str | None = None
    device_identifier: str | None = None

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("content must not be empty")

        if not self.original_filename.strip():
            raise ValueError("original_filename must not be empty")

        if not self.mime_type.strip():
            raise ValueError("mime_type must not be empty")

        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty")

        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")

        if self.source_type is EvidenceSourceType.AI_CAPTURE:
            if self.source_detection_id is None:
                raise ValueError("AI_CAPTURE evidence requires source_detection_id")

            if self.source_artifact_id is None:
                raise ValueError("AI_CAPTURE evidence requires source_artifact_id")

        if (
            self.source_type is EvidenceSourceType.MANUAL_UPLOAD
            and self.submitted_by_user_id is None
        ):
            raise ValueError("MANUAL_UPLOAD evidence requires submitted_by_user_id")


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceIngestionResult:
    evidence_id: UUID
    evidence_number: str

    custody_record_id: UUID
    audit_log_id: UUID

    storage_bucket: str
    storage_object_key: str
    storage_version_id: str | None

    original_sha256: str
    encrypted_sha256: str
    manifest_sha256: str


class SecureEvidenceIngestionService:
    """Coordinate secure forensic evidence ingestion."""

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
        self.custody = CustodyRepository(session)
        self.audit = AuditRepository(session)

    async def ingest(
        self,
        *,
        command: EvidenceIngestionCommand,
    ) -> EvidenceIngestionResult:
        await self._preflight_references(command)

        captured_at = command.captured_at.astimezone(UTC)

        ingested_at = datetime.now(UTC)

        evidence_number = generate_evidence_number(captured_at=captured_at)

        original = analyze_evidence_bytes(command.content)

        manifest = EvidenceForensicManifest(
            evidence_number=evidence_number,
            incident_id=command.incident_id,
            source_detection_id=(command.source_detection_id),
            source_type=command.source_type,
            evidence_type=command.evidence_type,
            original_filename=(command.original_filename),
            mime_type=command.mime_type,
            file_size_bytes=(original.file_size_bytes),
            original_sha256=(original.sha256),
            captured_at=captured_at,
        )

        manifest_artifact = build_manifest_artifact(manifest)

        secured = secure_evidence(
            command.content,
            manifest=manifest_artifact,
            key_wrapper=self.key_wrapper,
        )

        object_key = build_evidence_object_key(
            incident_id=(command.incident_id),
            evidence_number=(evidence_number),
            captured_at=captured_at,
            encrypted_sha256=(secured.encrypted_sha256),
        )

        stored = await self.storage.put_object(
            object_key=object_key,
            payload=(secured.encrypted_payload),
            content_type=("application/octet-stream"),
            metadata={
                "Evidence-Number": (evidence_number),
                "Incident-ID": str(command.incident_id),
                "Original-SHA256": (original.sha256),
                "Manifest-SHA256": (manifest_artifact.sha256),
                "Encrypted-SHA256": (secured.encrypted_sha256),
                "Envelope-Version": str(secured.envelope_version),
            },
        )

        try:
            await self._validate_references(
                command,
                lock=True,
            )

            signature_payload = build_evidence_signature_payload(
                evidence_number=(evidence_number),
                incident_id=(command.incident_id),
                source_detection_id=(command.source_detection_id),
                storage_bucket=(stored.bucket),
                storage_object_key=(stored.object_key),
                storage_version_id=(stored.version_id),
                original_sha256=(original.sha256),
                encrypted_sha256=(secured.encrypted_sha256),
                manifest_sha256=(manifest_artifact.sha256),
                captured_at=captured_at,
                ingested_at=ingested_at,
            )

            evidence_signature = self.signer.sign(signature_payload)

            record = PreparedEvidenceRecord(
                evidence_number=(evidence_number),
                incident_id=(command.incident_id),
                source_detection_id=(command.source_detection_id),
                submitted_by_user_id=(command.submitted_by_user_id),
                source_type=(command.source_type),
                evidence_type=(command.evidence_type),
                original_filename=(command.original_filename),
                mime_type=command.mime_type,
                file_size_bytes=(original.file_size_bytes),
                storage_bucket=(stored.bucket),
                storage_object_key=(stored.object_key),
                storage_version_id=(stored.version_id),
                original_sha256=(original.sha256),
                encrypted_sha256=(secured.encrypted_sha256),
                manifest_sha256=(manifest_artifact.sha256),
                digital_signature=(evidence_signature.to_json()),
                status=EvidenceStatus.STORED,
                captured_at=captured_at,
                ingested_at=ingested_at,
                source_artifact_id=(command.source_artifact_id),
            )

            evidence = await self.evidence.create(record=record)

            await self.evidence.create_key(
                evidence_id=evidence.id,
                key=PreparedEvidenceKey(
                    algorithm=(secured.wrapped_key.algorithm),
                    wrapped_key=(secured.wrapped_key.wrapped_key),
                    key_reference=(secured.wrapped_key.key_reference),
                    key_version=(secured.wrapped_key.key_version),
                    is_active=True,
                ),
            )

            existing_custody = await self.custody.get_latest_for_update(evidence_id=evidence.id)

            if existing_custody is not None:
                raise RuntimeError("New evidence unexpectedly already has custody records")

            custody_metadata: dict[
                str,
                object,
            ] = {
                "correlation_id": (command.correlation_id),
                "evidence_number": (evidence_number),
                "source_type": (command.source_type.value),
                "storage_bucket": (stored.bucket),
                "storage_object_key": (stored.object_key),
                "storage_version_id": (stored.version_id),
                "original_sha256": (original.sha256),
                "encrypted_sha256": (secured.encrypted_sha256),
                "manifest_sha256": (manifest_artifact.sha256),
            }

            custody_integrity = build_custody_integrity(
                evidence_id=evidence.id,
                actor_user_id=(command.submitted_by_user_id),
                from_user_id=None,
                to_user_id=None,
                previous_record_id=None,
                previous_record_hash=None,
                transfer_id=None,
                event_type=(CustodyEventType.ACQUIRED),
                purpose=("Initial secure evidence acquisition"),
                source_ip=(command.source_ip),
                device_identifier=(command.device_identifier),
                event_metadata=(custody_metadata),
                occurred_at=ingested_at,
            )

            custody_signature = self.signer.sign(custody_integrity.canonical_bytes)

            custody_record = await self.custody.create(
                evidence_id=evidence.id,
                actor_user_id=(command.submitted_by_user_id),
                from_user_id=None,
                to_user_id=None,
                previous_record_id=None,
                transfer_id=None,
                event_type=(CustodyEventType.ACQUIRED),
                purpose=("Initial secure evidence acquisition"),
                source_ip=(command.source_ip),
                device_identifier=(command.device_identifier),
                event_metadata=(custody_metadata),
                record_hash=(custody_integrity.record_hash),
                digital_signature=(custody_signature.to_json()),
                occurred_at=ingested_at,
            )

            audit_log = await self.audit.create(
                actor_user_id=(command.submitted_by_user_id),
                action=(AuditAction.EVIDENCE_INGESTED),
                resource_type="evidence",
                resource_id=evidence.id,
                outcome=(AuditOutcome.SUCCESS),
                correlation_id=(command.correlation_id),
                occurred_at=(ingested_at),
                source_ip=(command.source_ip),
                user_agent=(command.user_agent),
                details={
                    "evidence_number": (evidence_number),
                    "incident_id": str(command.incident_id),
                    "source_detection_id": (
                        str(command.source_detection_id) if command.source_detection_id else None
                    ),
                    "storage_bucket": (stored.bucket),
                    "storage_object_key": (stored.object_key),
                    "storage_version_id": (stored.version_id),
                    "custody_record_id": (str(custody_record.id)),
                    "original_sha256": (original.sha256),
                    "encrypted_sha256": (secured.encrypted_sha256),
                    "manifest_sha256": (manifest_artifact.sha256),
                },
            )

            await self.session.commit()

        except asyncio.CancelledError:
            await self.session.rollback()

            await self._compensate_storage(stored)

            raise

        except Exception:
            await self.session.rollback()

            await self._compensate_storage(stored)

            raise

        return EvidenceIngestionResult(
            evidence_id=evidence.id,
            evidence_number=evidence_number,
            custody_record_id=(custody_record.id),
            audit_log_id=audit_log.id,
            storage_bucket=stored.bucket,
            storage_object_key=(stored.object_key),
            storage_version_id=(stored.version_id),
            original_sha256=(original.sha256),
            encrypted_sha256=(secured.encrypted_sha256),
            manifest_sha256=(manifest_artifact.sha256),
        )

    async def _preflight_references(
        self,
        command: EvidenceIngestionCommand,
    ) -> None:
        try:
            await self._validate_references(
                command,
                lock=False,
            )
        finally:
            if self.session.in_transaction():
                await self.session.rollback()

    async def _validate_references(
        self,
        command: EvidenceIngestionCommand,
        *,
        lock: bool,
    ) -> None:
        incident_statement = select(Incident).where(Incident.id == command.incident_id)

        if lock:
            incident_statement = incident_statement.with_for_update()

        incident_result = await self.session.execute(incident_statement)

        incident = incident_result.scalar_one_or_none()

        if incident is None:
            raise EvidenceReferenceError("Referenced incident does not exist")

        if command.source_detection_id is None:
            return

        detection_statement = select(DetectionEvent).where(
            DetectionEvent.id == command.source_detection_id
        )

        if lock:
            detection_statement = detection_statement.with_for_update()

        detection_result = await self.session.execute(detection_statement)

        detection = detection_result.scalar_one_or_none()

        if detection is None:
            raise EvidenceReferenceError("Referenced detection event does not exist")

        if detection.incident_id != command.incident_id:
            raise EvidenceReferenceError("Detection event is not linked to the supplied incident")

    async def _compensate_storage(
        self,
        stored: StoredEvidenceObject,
    ) -> None:
        try:
            await self.storage.delete_for_compensation(
                object_key=(stored.object_key),
                version_id=(stored.version_id),
            )

        except EvidenceObjectNotFoundError:
            return

        except Exception as exception:
            raise (
                EvidenceIngestionCompensationError(
                    "PostgreSQL evidence transaction failed and MinIO compensation also failed"
                )
            ) from exception
