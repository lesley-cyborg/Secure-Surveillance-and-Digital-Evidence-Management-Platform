from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.incidents import Incident  # adjust import path
from app.db.models.surveillance import Camera  # adjust
from app.db.models.evidence import Evidence  # adjust
from app.modules.reports.csv_util import build_csv


def _cutoff(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def export_incidents_csv(
    session: AsyncSession,
    *,
    days: int = 7,
    camera_id: UUID | None = None,
    status: str | None = None,
) -> str:
    cutoff = _cutoff(days)
    stmt = select(Incident).where(
        (Incident.detected_at >= cutoff) | (Incident.created_at >= cutoff)
    )
    if camera_id is not None:
        stmt = stmt.where(Incident.primary_camera_id == camera_id)
    if status:
        stmt = stmt.where(Incident.status == status)
    stmt = stmt.order_by(Incident.created_at.desc()).limit(5000)

    result = await session.scalars(stmt)
    rows = result.all()

    return build_csv(
        [
            "id",
            "incident_number",
            "title",
            "status",
            "severity",
            "priority",
            "source_type",
            "incident_type",
            "primary_camera_id",
            "detected_at",
            "created_at",
            "closed_at",
        ],
        [
            (
                r.id,
                r.incident_number,
                r.title,
                r.status,
                r.severity,
                r.priority,
                r.source_type,
                r.incident_type,
                r.primary_camera_id,
                r.detected_at,
                r.created_at,
                r.closed_at,
            )
            for r in rows
        ],
    )


async def export_analytics_summary_csv(
    session: AsyncSession,
    *,
    days: int = 7,
    camera_id: UUID | None = None,
) -> str:
    cutoff = _cutoff(days)
    stmt = select(Incident).where(
        (Incident.detected_at >= cutoff) | (Incident.created_at >= cutoff)
    )
    if camera_id is not None:
        stmt = stmt.where(Incident.primary_camera_id == camera_id)
    stmt = stmt.limit(5000)
    incidents = list(await session.scalars(stmt))

    cameras = list(await session.scalars(select(Camera).limit(2000)))
    evidence = list(await session.scalars(select(Evidence).limit(2000)))

    by_status = Counter(str(i.status) for i in incidents)
    by_severity = Counter(str(i.severity) for i in incidents)
    by_source = Counter(str(i.source_type) for i in incidents)
    cam_status = Counter(str(c.status) for c in cameras)
    ev_status = Counter(str(getattr(e, "status", "UNKNOWN")) for e in evidence)

    # Multi-section CSV as sequential blocks
    parts: list[str] = []
    parts.append(
        build_csv(
            ["section", "key", "value"],
            [
                ("summary", "days", days),
                ("summary", "camera_id", str(camera_id) if camera_id else "ALL"),
                ("summary", "incident_count", len(incidents)),
                ("summary", "camera_count", len(cameras)),
                ("summary", "evidence_count", len(evidence)),
            ],
        )
    )
    parts.append(
        build_csv(
            ["status", "count"],
            list(by_status.items()),
        )
    )
    parts.append(
        build_csv(
            ["severity", "count"],
            list(by_severity.items()),
        )
    )
    parts.append(
        build_csv(
            ["source_type", "count"],
            list(by_source.items()),
        )
    )
    parts.append(
        build_csv(
            ["camera_status", "count"],
            list(cam_status.items()),
        )
    )
    parts.append(
        build_csv(
            ["evidence_status", "count"],
            list(ev_status.items()),
        )
    )
    return "\r\n".join(parts)