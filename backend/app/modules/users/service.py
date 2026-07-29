from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models.enums import AuditOutcome
from app.db.models.identity import User
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import AuditRepository
from app.modules.auth.repository import (
    AuthSessionRepository,
    UserRepository,
)
from app.modules.auth.token_store import (
    NullTokenRevocationStore,
    TokenRevocationStore,
)
from app.modules.rbac.repository import (
    RBACRepository,
)
from app.modules.users.exceptions import (
    DuplicateUserError,
    LastAdministratorError,
    RoleAlreadyAssignedError,
    RoleAssignmentNotFoundError,
    RoleNotFoundError,
    SelfModificationForbiddenError,
    UserNotFoundError,
)
from app.modules.users.schemas import (
    UserCreateRequest,
)

logger = logging.getLogger(__name__)

ADMINISTRATOR_ROLE_NAME = "ADMINISTRATOR"


@dataclass(frozen=True, slots=True)
class UserManagementContext:
    actor_user_id: UUID
    correlation_id: str
    source_ip: str | None
    user_agent: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class UserManagementService:
    def __init__(
        self,
        session: AsyncSession,
        revocations: TokenRevocationStore | None = None,
    ) -> None:
        self.session = session

        self.users = UserRepository(session)
        self.sessions = AuthSessionRepository(session)
        self.rbac = RBACRepository(session)
        self.audit = AuditRepository(session)

        self.revocations = revocations or NullTokenRevocationStore()

    async def create_user(
        self,
        *,
        payload: UserCreateRequest,
        context: UserManagementContext,
    ) -> User:
        now = _utc_now()

        try:
            existing_email = await self.users.get_by_email(
                payload.email,
                include_deleted=True,
            )

            if existing_email is not None:
                raise DuplicateUserError("email_already_exists")

            existing_username = await self.users.get_by_username(
                payload.username,
                include_deleted=True,
            )

            if existing_username is not None:
                raise DuplicateUserError("username_already_exists")

            roles = []

            for role_id in payload.role_ids:
                role = await self.rbac.get_role_by_id(role_id)

                if role is None:
                    raise RoleNotFoundError(f"role_not_found:{role_id}")

                roles.append(role)

            user = await self.users.create(
                email=payload.email,
                username=payload.username,
                password_hash=hash_password(payload.password.get_secret_value()),
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone=payload.phone,
                is_active=True,
            )

            for role in roles:
                await self.rbac.assign_role(
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by=(context.actor_user_id),
                    assigned_at=now,
                    expires_at=None,
                )

                await self.audit.create(
                    actor_user_id=(context.actor_user_id),
                    action=(AuditAction.RBAC_ROLE_ASSIGNED),
                    resource_type="user_role",
                    resource_id=user.id,
                    outcome=AuditOutcome.SUCCESS,
                    correlation_id=(context.correlation_id),
                    occurred_at=now,
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    details={
                        "target_user_id": str(user.id),
                        "role_id": str(role.id),
                        "role_name": role.name,
                    },
                )

            await self.audit.create(
                actor_user_id=(context.actor_user_id),
                action=AuditAction.USER_CREATED,
                resource_type="user",
                resource_id=user.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(context.correlation_id),
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "email": user.email,
                    "username": user.username,
                    "role_ids": [str(role.id) for role in roles],
                },
            )

            await self.session.commit()

            return user

        except DuplicateUserError:
            await self.session.rollback()
            raise

        except IntegrityError as exc:
            await self.session.rollback()

            raise DuplicateUserError("email_or_username_already_exists") from exc

        except Exception:
            await self.session.rollback()
            raise

    async def list_users(
        self,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]:
        users = await self.users.list_users(
            offset=offset,
            limit=limit,
        )

        total = await self.users.count_users()

        return users, total

    async def get_user(
        self,
        user_id: UUID,
    ) -> User:
        user = await self.users.get_by_id(user_id)

        if user is None:
            raise UserNotFoundError("user_not_found")

        return user

    async def set_active_status(
        self,
        *,
        user_id: UUID,
        is_active: bool,
        context: UserManagementContext,
    ) -> User:
        now = _utc_now()

        try:
            user = await self.users.get_by_id_for_update(
                user_id,
                include_deleted=True,
            )

            if user is None or user.deleted_at is not None:
                raise UserNotFoundError("user_not_found")

            if user.is_active == is_active:
                await self.session.commit()
                return user

            revoked_session_ids: list[UUID] = []

            if not is_active:
                if user.id == context.actor_user_id:
                    raise SelfModificationForbiddenError("cannot_deactivate_current_user")

                await self._assert_not_last_admin(
                    user_id=user.id,
                    now=now,
                )

                revoked_session_ids = await self.sessions.revoke_all_active_for_user(
                    user.id,
                    revoked_at=now,
                )

                action = AuditAction.USER_DEACTIVATED

            else:
                action = AuditAction.USER_ACTIVATED

            await self.users.set_active_status(
                user,
                is_active=is_active,
            )

            await self.audit.create(
                actor_user_id=(context.actor_user_id),
                action=action,
                resource_type="user",
                resource_id=user.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(context.correlation_id),
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "is_active": is_active,
                    "revoked_session_ids": [str(session_id) for session_id in revoked_session_ids],
                },
            )

            await self.session.commit()

            if revoked_session_ids:
                await self._mark_sessions_revoked(revoked_session_ids)

            return user

        except Exception:
            await self.session.rollback()
            raise

    async def assign_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
        context: UserManagementContext,
    ) -> None:
        now = _utc_now()

        try:
            user = await self.users.get_by_id_for_update(
                user_id,
                include_deleted=True,
            )

            if user is None or user.deleted_at is not None:
                raise UserNotFoundError("user_not_found")

            role = await self.rbac.get_role_by_id(role_id)

            if role is None:
                raise RoleNotFoundError("role_not_found")

            already_assigned = await self.rbac.user_has_role(
                user_id=user.id,
                role_id=role.id,
                now=now,
            )

            if already_assigned:
                raise RoleAlreadyAssignedError("role_already_assigned")

            await self.rbac.assign_role(
                user_id=user.id,
                role_id=role.id,
                assigned_by=(context.actor_user_id),
                assigned_at=now,
                expires_at=None,
            )

            await self.audit.create(
                actor_user_id=(context.actor_user_id),
                action=(AuditAction.RBAC_ROLE_ASSIGNED),
                resource_type="user_role",
                resource_id=user.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(context.correlation_id),
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "target_user_id": str(user.id),
                    "role_id": str(role.id),
                    "role_name": role.name,
                },
            )

            await self.session.commit()

        except IntegrityError as exc:
            await self.session.rollback()

            raise RoleAlreadyAssignedError("role_already_assigned") from exc

        except Exception:
            await self.session.rollback()
            raise

    async def remove_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
        context: UserManagementContext,
    ) -> None:
        now = _utc_now()

        try:
            user = await self.users.get_by_id_for_update(
                user_id,
                include_deleted=True,
            )

            if user is None or user.deleted_at is not None:
                raise UserNotFoundError("user_not_found")

            role = await self.rbac.get_role_by_id(role_id)

            if role is None:
                raise RoleNotFoundError("role_not_found")

            if role.name.casefold() == ADMINISTRATOR_ROLE_NAME.casefold():
                if user.id == context.actor_user_id:
                    raise SelfModificationForbiddenError("cannot_remove_own_administrator_role")

                administrators = await self.rbac.count_active_users_with_role(
                    role_id=role.id,
                    now=now,
                )

                if administrators <= 1:
                    raise LastAdministratorError("cannot_remove_last_administrator")

            removed = await self.rbac.remove_role(
                user_id=user.id,
                role_id=role.id,
            )

            if not removed:
                raise RoleAssignmentNotFoundError("role_assignment_not_found")

            await self.audit.create(
                actor_user_id=(context.actor_user_id),
                action=(AuditAction.RBAC_ROLE_REMOVED),
                resource_type="user_role",
                resource_id=user.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=(context.correlation_id),
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "target_user_id": str(user.id),
                    "role_id": str(role.id),
                    "role_name": role.name,
                },
            )

            await self.session.commit()

        except Exception:
            await self.session.rollback()
            raise

    async def _assert_not_last_admin(
        self,
        *,
        user_id: UUID,
        now: datetime,
    ) -> None:
        administrator_role = await self.rbac.get_role_by_name(ADMINISTRATOR_ROLE_NAME)

        if administrator_role is None:
            return

        is_administrator = await self.rbac.user_has_role(
            user_id=user_id,
            role_id=administrator_role.id,
            now=now,
        )

        if not is_administrator:
            return

        administrator_count = await self.rbac.count_active_users_with_role(
            role_id=administrator_role.id,
            now=now,
        )

        if administrator_count <= 1:
            raise LastAdministratorError("cannot_deactivate_last_administrator")

    async def _mark_sessions_revoked(
        self,
        session_ids: list[UUID],
    ) -> None:
        try:
            await self.revocations.revoke_sessions(session_ids)
        except RedisError:
            logger.exception("Could not write user-session revocations to Redis")
