from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.db.models.enums import AuditOutcome
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import AuditRepository
from app.modules.auth.repository import UserRepository
from app.modules.rbac.repository import RBACRepository
from sqlalchemy.ext.asyncio import AsyncSession


class RBACServiceError(Exception):
    """Base exception for RBAC service operations."""


class RBACUserNotFoundError(RBACServiceError):
    """Raised when the target user does not exist."""


class RBACRoleNotFoundError(RBACServiceError):
    """Raised when the requested role does not exist."""


class RBACAssignmentNotFoundError(RBACServiceError):
    """Raised when a requested role assignment does not exist."""


@dataclass(frozen=True, slots=True)
class RBACOperationContext:
    actor_user_id: UUID
    correlation_id: str
    source_ip: str | None
    user_agent: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class RBACService:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

        self.users = UserRepository(session)
        self.rbac = RBACRepository(session)
        self.audit = AuditRepository(session)

    async def assign_role(
        self,
        *,
        target_user_id: UUID,
        role_id: UUID,
        context: RBACOperationContext,
        expires_at: datetime | None = None,
    ) -> None:
        now = _utc_now()

        try:
            target_user = await self.users.get_by_id_for_update(
                target_user_id,
                include_deleted=True,
            )

            if target_user is None or target_user.deleted_at is not None:
                raise RBACUserNotFoundError("target_user_not_found")

            role = await self.rbac.get_role_by_id(role_id)

            if role is None:
                raise RBACRoleNotFoundError("role_not_found")

            await self.rbac.assign_role(
                user_id=target_user_id,
                role_id=role_id,
                assigned_by=(context.actor_user_id),
                assigned_at=now,
                expires_at=expires_at,
            )

            await self.audit.create(
                actor_user_id=(context.actor_user_id),
                action=(AuditAction.RBAC_ROLE_ASSIGNED),
                resource_type="user_role",
                resource_id=target_user_id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(context.correlation_id),
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "target_user_id": str(target_user_id),
                    "role_id": str(role_id),
                    "role_name": role.name,
                    "expires_at": (expires_at.isoformat() if expires_at is not None else None),
                },
            )

            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise

    async def remove_role(
        self,
        *,
        target_user_id: UUID,
        role_id: UUID,
        context: RBACOperationContext,
    ) -> None:
        now = _utc_now()

        try:
            target_user = await self.users.get_by_id_for_update(
                target_user_id,
                include_deleted=True,
            )

            if target_user is None or target_user.deleted_at is not None:
                raise RBACUserNotFoundError("target_user_not_found")

            role = await self.rbac.get_role_by_id(role_id)

            if role is None:
                raise RBACRoleNotFoundError("role_not_found")

            removed = await self.rbac.remove_role(
                user_id=target_user_id,
                role_id=role_id,
            )

            if not removed:
                raise RBACAssignmentNotFoundError("role_assignment_not_found")

            await self.audit.create(
                actor_user_id=(context.actor_user_id),
                action=(AuditAction.RBAC_ROLE_REMOVED),
                resource_type="user_role",
                resource_id=target_user_id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(context.correlation_id),
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "target_user_id": str(target_user_id),
                    "role_id": str(role_id),
                    "role_name": role.name,
                },
            )

            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise
