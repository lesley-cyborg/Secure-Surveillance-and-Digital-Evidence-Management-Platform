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

router = APIRouter(prefix="/incidents", tags=["Incidents"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


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
    # Get total count for pagination
    count_stmt = select(func.count()).select_from(Incident)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get items ordered by most recent detection
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
