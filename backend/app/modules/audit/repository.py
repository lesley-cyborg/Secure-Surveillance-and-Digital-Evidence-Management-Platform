from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import AuditOutcome
from app.db.models.reporting import AuditLog


class AuditRepository:
    """Persistence operations for forensic audit events."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def create(
        self,
        *,
        action: str,
        resource_type: str,
        outcome: AuditOutcome,
        correlation_id: str,
        occurred_at: datetime,
        actor_user_id: UUID | None = None,
        resource_id: UUID | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        details: dict[str, object] | None = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            actor_user_id=actor_user_id,
            action=action.strip(),
            resource_type=resource_type.strip(),
            resource_id=resource_id,
            outcome=outcome,
            source_ip=source_ip,
            user_agent=user_agent,
            correlation_id=correlation_id.strip(),
            details=details or {},
            occurred_at=occurred_at,
        )

        self.session.add(audit_log)
        await self.session.flush()

        return audit_log