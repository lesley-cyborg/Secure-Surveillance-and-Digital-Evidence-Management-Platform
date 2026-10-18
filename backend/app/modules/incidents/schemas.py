from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# Import your Enums from your db models
from app.db.models.enums import (
    IncidentSourceType,
    IncidentStatus,
    Priority,
    Severity,
)


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class IncidentResponse(APIModel):
    id: UUID
    incident_number: str
    primary_camera_id: UUID | None = None
    source_type: IncidentSourceType
    incident_type: str
    severity: Severity
    priority: Priority
    status: IncidentStatus
    title: str
    description: str | None = None
    disposition: str | None = None
    detected_at: datetime
    confirmed_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(APIModel):
    items: list[IncidentResponse]
    total: int