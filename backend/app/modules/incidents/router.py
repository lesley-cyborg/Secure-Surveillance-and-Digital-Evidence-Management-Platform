import os
import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.incidents import Incident
from app.db.session import get_db_session
from app.modules.incidents.schemas import IncidentListResponse, IncidentResponse
from app.modules.rbac.dependencies import (
    AuthorizationContext,
    require_permission,
)

from app.db.models.evidence import CustodyRecord, Evidence
from app.db.models.enums import (
    CustodyEventType,
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
)

router = APIRouter(prefix="/incidents", tags=["Incidents"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]

# 👇 Define storage path
STORAGE_BASE = Path(__file__).parent.parent.parent / "storage" / "evidence"
STORAGE_BASE.mkdir(parents=True, exist_ok=True)


def _to_response(incident: Incident) -> IncidentResponse:
    return IncidentResponse(
        id=incident.id,
        incident_number=incident.incident_number,
        primary_camera_id=incident.primary_camera_id,
        source_type=incident.source_type,
        incident_type=incident.incident_type,
        severity=incident.severity,
        priority=incident.priority,
        status=incident.status,
        title=incident.title,
        description=incident.description,
        disposition=incident.disposition,
        detected_at=incident.detected_at,
        confirmed_at=incident.confirmed_at,
        closed_at=incident.closed_at,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


@router.get(
    "",
    response_model=IncidentListResponse,
    response_model_by_alias=True,
    summary="List incidents",
)
async def list_incidents(
    session: DbSession,
    _: Annotated[AuthorizationContext, Depends(require_permission("incidents.read"))],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> IncidentListResponse:
    count_stmt = select(func.count()).select_from(Incident)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = (
        select(Incident)
        .order_by(Incident.detected_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    incidents = list(result.scalars().all())

    return IncidentListResponse(
        items=[_to_response(inc) for inc in incidents],
        total=total,
    )


@router.post(
    "/{incident_id}/create-evidence",
    status_code=status.HTTP_201_CREATED,
    summary="Manually create evidence from an incident",
)
async def create_manual_evidence(
    incident_id: UUID,
    session: DbSession,
    authorization: Annotated[AuthorizationContext, Depends(require_permission("incidents.update"))],
):
    # 1. Verify incident exists
    result = await session.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Incident not found"
        )

    # 2. Generate mock evidence data
    fake_filename = f"weapon_detection_{incident_id}.jpg"
    fake_content = b"mock_image_data_for_weapon_detection"
    
    original_sha256 = hashlib.sha256(fake_content).hexdigest()
    encrypted_sha256 = hashlib.sha256(b"encrypted_" + fake_content).hexdigest()
    manifest_sha256 = hashlib.sha256(b"manifest_" + fake_content).hexdigest()
    digital_signature = f"sig_{secrets.token_hex(32)}"
    
    # 3. PHYSICALLY SAVE THE FILE TO LOCAL STORAGE 
    storage_path = STORAGE_BASE / f"{incident_id}_{original_sha256}.jpg"
    with open(storage_path, "wb") as f:
        f.write(fake_content)
    
    storage_object_key = f"{incident_id}_{original_sha256}.jpg"

    # 4. Create Evidence record
    evidence = Evidence(
        evidence_number=f"EVD-{incident.incident_number}-001",
        incident_id=incident_id,
        source_type=EvidenceSourceType.AI_CAPTURE,  
        evidence_type=EvidenceType.IMAGE,   
        original_filename=fake_filename,
        mime_type="image/jpeg",
        file_size_bytes=len(fake_content),
        storage_bucket="local-storage",
        storage_object_key=storage_object_key,
        original_sha256=original_sha256,
        encrypted_sha256=encrypted_sha256,
        manifest_sha256=manifest_sha256,
        digital_signature=digital_signature,
        status=EvidenceStatus.STORED,  # Changed to STORED since file is saved
        captured_at=incident.detected_at,
        ingested_at=datetime.now(timezone.utc),
    )
    session.add(evidence)
    await session.flush()

    # 5. Create the initial Chain of Custody Record
    custody_record = CustodyRecord(
        evidence_id=evidence.id,
        event_type=CustodyEventType.ACQUIRED,
        purpose="Initial evidence ingestion from AI weapon detection",
        actor_user_id=authorization.user.id,  # ADD THIS - Set current user as custodian
        previous_record_id=None,  # First record has no previous
        record_hash=hashlib.sha256(f"custody_{evidence.id}".encode()).hexdigest(),
        digital_signature=f"custody_sig_{secrets.token_hex(32)}",
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(custody_record)
    await session.commit()

    return {
        "message": "Evidence and initial custody record created successfully",
        "evidence_id": str(evidence.id),
        "evidence_number": evidence.evidence_number
    }