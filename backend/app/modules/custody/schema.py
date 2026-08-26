from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.db.models.enums import CustodyEventType


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class CreateCustodyEventRequest(APIModel):
    event_type: CustodyEventType = Field(alias="eventType")
    purpose: str = Field(min_length=3, max_length=1000)
    event_metadata: dict[str, Any] | None = Field(
        default_factory=dict,
        alias="eventMetadata",
    )


class CustodyEventResponse(APIModel):
    id: UUID
    evidence_id: UUID
    actor_user_id: UUID
    from_user_id: UUID | None = None
    to_user_id: UUID | None = None
    previous_record_id: UUID | None = None
    event_type: CustodyEventType
    purpose: str | None = None
    source_ip: str | None = None
    device_identifier: str | None = None
    event_metadata: dict[str, Any] | None = None
    record_hash: str
    digital_signature: str
    occurred_at: datetime


class PaginationMeta(APIModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class CustodyEventPageResponse(APIModel):
    items: list[CustodyEventResponse]
    pagination: PaginationMeta