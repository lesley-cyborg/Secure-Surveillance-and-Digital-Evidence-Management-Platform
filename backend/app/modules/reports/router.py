from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.rbac.dependencies import (
    AuthorizationContext,
    require_permission,
)
from app.modules.reports.service import (
    export_analytics_summary_csv,
    export_incidents_csv,
)

router = APIRouter(prefix="/reports", tags=["Reports"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def _csv_response(body: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/export/incidents",
    summary="Export incidents as CSV",
    name="export_incidents_csv",
)
async def export_incidents(
    session: DbSession,
    _: Annotated[
        AuthorizationContext,
        Depends(require_permission("reports.export")),
    ],
    # Changed from Literal[7, 14, 30] to int with ge=1, le=30 constraints
    days: Annotated[int, Query(ge=1, le=30)] = 7,
    camera_id: Annotated[UUID | None, Query(alias="cameraId")] = None,
    status: Annotated[str | None, Query()] = None,
) -> Response:
    csv_body = await export_incidents_csv(
        session,
        days=days,
        camera_id=camera_id,
        status=status,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _csv_response(csv_body, f"incidents-{days}d-{stamp}.csv")


@router.get(
    "/export/analytics-summary",
    summary="Export analytics summary as CSV",
    name="export_analytics_summary_csv",
)
async def export_analytics_summary(
    session: DbSession,
    _: Annotated[
        AuthorizationContext,
        Depends(require_permission("reports.export")),
    ],
    # Changed from Literal[7, 14, 30] to int with ge=1, le=30 constraints
    days: Annotated[int, Query(ge=1, le=30)] = 7,
    camera_id: Annotated[UUID | None, Query(alias="cameraId")] = None,
) -> Response:
    csv_body = await export_analytics_summary_csv(
        session,
        days=days,
        camera_id=camera_id,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _csv_response(csv_body, f"analytics-summary-{days}d-{stamp}.csv")