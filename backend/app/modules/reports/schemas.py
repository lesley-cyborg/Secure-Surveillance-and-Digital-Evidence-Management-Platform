from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ExportQuery(BaseModel):
    days: Literal[7, 14, 30] = 7
    camera_id: UUID | None = Field(default=None, alias="cameraId")
    status: str | None = None

    model_config = {"populate_by_name": True}