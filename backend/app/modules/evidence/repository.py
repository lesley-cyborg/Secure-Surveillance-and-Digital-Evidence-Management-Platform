from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    EvidenceStatus,
    VerificationStatus,
)
from app.db.models.evidence import (
    Evidence,
    EvidenceKey,
    EvidenceVerification,
)
from app.modules.evidence.contracts import (
    PreparedEvidenceKey,
    PreparedEvidenceRecord,
)


class EvidenceRepository:
    """Database operations for forensic evidence.

    Repositories flush but never commit. Transaction
    boundaries belong to the service layer.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def create(
        self,
        *,
        record: PreparedEvidenceRecord,
    ) -> Evidence:
        evidence = Evidence(
            evidence_number=(record.evidence_number),
            incident_id=record.incident_id,
            source_detection_id=(record.source_detection_id),
            source_artifact_id=(record.source_artifact_id),
            submitted_by_user_id=(record.submitted_by_user_id),
            source_type=record.source_type,
            evidence_type=record.evidence_type,
            original_filename=(record.original_filename),
            mime_type=record.mime_type,
            file_size_bytes=(record.file_size_bytes),
            storage_bucket=(record.storage_bucket),
            storage_object_key=(record.storage_object_key),
            storage_version_id=(record.storage_version_id),
            original_sha256=(record.original_sha256),
            encrypted_sha256=(record.encrypted_sha256),
            manifest_sha256=(record.manifest_sha256),
            digital_signature=(record.digital_signature),
            status=record.status,
            captured_at=record.captured_at,
            ingested_at=record.ingested_at,
        )

        self.session.add(evidence)
        await self.session.flush()

        return evidence

    async def create_key(
        self,
        *,
        evidence_id: UUID,
        key: PreparedEvidenceKey,
    ) -> EvidenceKey:
        evidence_key = EvidenceKey(
            evidence_id=evidence_id,
            algorithm=key.algorithm,
            wrapped_key=key.wrapped_key,
            key_reference=key.key_reference,
            key_version=key.key_version,
            is_active=key.is_active,
            rotated_at=None,
        )

        self.session.add(evidence_key)
        await self.session.flush()

        return evidence_key

    async def get_by_id(
        self,
        evidence_id: UUID,
    ) -> Evidence | None:
        return await self.session.get(
            Evidence,
            evidence_id,
        )

    async def get_by_id_for_update(
        self,
        evidence_id: UUID,
    ) -> Evidence | None:
        statement = select(Evidence).where(Evidence.id == evidence_id).with_for_update()

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_evidence_number(
        self,
        evidence_number: str,
    ) -> Evidence | None:
        statement = select(Evidence).where(Evidence.evidence_number == evidence_number)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_storage_object_key(
        self,
        storage_object_key: str,
    ) -> Evidence | None:
        statement = select(Evidence).where(Evidence.storage_object_key == storage_object_key)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_active_key(
        self,
        evidence_id: UUID,
    ) -> EvidenceKey | None:
        statement = select(EvidenceKey).where(
            EvidenceKey.evidence_id == evidence_id,
            EvidenceKey.is_active.is_(True),
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_source_artifact_id(
        self,
        source_artifact_id: UUID,
    ) -> Evidence | None:
        statement = select(Evidence).where(Evidence.source_artifact_id == source_artifact_id)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def create_verification(
        self,
        *,
        evidence_id: UUID,
        verified_by_user_id: UUID | None,
        expected_sha256: str,
        calculated_sha256: str | None,
        hash_matches: bool,
        signature_valid: bool,
        verification_status: VerificationStatus,
        failure_reason: str | None,
        verified_at: datetime,
        idempotency_key: str | None = None,
    ) -> EvidenceVerification:
        verification = EvidenceVerification(
            evidence_id=evidence_id,
            verified_by_user_id=verified_by_user_id,
            idempotency_key=idempotency_key,
            expected_sha256=expected_sha256,
            calculated_sha256=calculated_sha256,
            hash_matches=hash_matches,
            signature_valid=signature_valid,
            verification_status=verification_status,
            failure_reason=failure_reason,
            verified_at=verified_at,
        )

        self.session.add(verification)

        await self.session.flush()

        return verification

    async def set_status(
        self,
        *,
        evidence: Evidence,
        status: EvidenceStatus,
    ) -> None:
        evidence.status = status

        await self.session.flush()

    async def get_verification_by_idempotency_key(
        self,
        *,
        evidence_id: UUID,
        idempotency_key: str,
    ) -> EvidenceVerification | None:
        statement = select(EvidenceVerification).where(
            EvidenceVerification.evidence_id == evidence_id,
            EvidenceVerification.idempotency_key == idempotency_key,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def list_evidence(
        self,
        *,
        incident_id: UUID | None = None,
        status_filter: EvidenceStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Evidence]:
        statement = select(Evidence).order_by(Evidence.ingested_at.desc())

        if incident_id is not None:
            statement = statement.where(Evidence.incident_id == incident_id)

        if status_filter is not None:
            statement = statement.where(Evidence.status == status_filter)

        statement = statement.limit(limit).offset(offset)

        result = await self.session.execute(statement)
        return list(result.scalars().all())


    async def count_evidence(
        self,
        *,
        incident_id: UUID | None = None,
        status_filter: EvidenceStatus | None = None,
    ) -> int:
        from sqlalchemy import func

        statement = select(func.count()).select_from(Evidence)

        if incident_id is not None:
            statement = statement.where(Evidence.incident_id == incident_id)

        if status_filter is not None:
            statement = statement.where(Evidence.status == status_filter)

        result = await self.session.execute(statement)
        return int(result.scalar_one())



