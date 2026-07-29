from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.db.models.identity import Permission, Role, RolePermission, User, UserRole
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class AccessSnapshot:
    user_id: UUID
    role_names: frozenset[str]
    permission_codes: frozenset[str]

    def has_role(self, role_name: str) -> bool:
        return role_name in self.role_names

    def has_permission(
        self,
        permission_code: str,
    ) -> bool:
        return permission_code in self.permission_codes


class RBACRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_role_by_id(
        self,
        role_id: UUID,
    ) -> Role | None:
        return await self.session.get(Role, role_id)

    async def get_role_by_name(
        self,
        name: str,
    ) -> Role | None:
        statement = select(Role).where(func.lower(Role.name) == name.strip().casefold())

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def user_has_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
        now: datetime,
    ) -> bool:
        statement = select(UserRole.user_id).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            (UserRole.expires_at.is_(None) | (UserRole.expires_at > now)),
        )

        result = await self.session.scalar(statement)

        return result is not None

    async def count_active_users_with_role(
        self,
        *,
        role_id: UUID,
        now: datetime,
    ) -> int:
        statement = (
            select(func.count(func.distinct(UserRole.user_id)))
            .join(
                User,
                User.id == UserRole.user_id,
            )
            .where(
                UserRole.role_id == role_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                (UserRole.expires_at.is_(None) | (UserRole.expires_at > now)),
            )
        )

        result = await self.session.scalar(statement)

        return int(result or 0)

    async def get_permission_by_code(
        self,
        permission_code: str,
    ) -> Permission | None:
        statement = select(Permission).where(Permission.code == permission_code.strip())

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def assign_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
        assigned_by: UUID | None,
        assigned_at: datetime,
        expires_at: datetime | None = None,
    ) -> UserRole:
        assignment = await self.session.get(
            UserRole,
            {
                "user_id": user_id,
                "role_id": role_id,
            },
        )

        if assignment is None:
            assignment = UserRole(
                user_id=user_id,
                role_id=role_id,
                assigned_by=assigned_by,
                assigned_at=assigned_at,
                expires_at=expires_at,
            )
            self.session.add(assignment)
        else:
            assignment.assigned_by = assigned_by
            assignment.assigned_at = assigned_at
            assignment.expires_at = expires_at

        await self.session.flush()
        return assignment

    async def remove_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
    ) -> bool:
        statement = delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )

        result = await self.session.execute(statement)
        await self.session.flush()

        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount)

    async def grant_permission(
        self,
        *,
        role_id: UUID,
        permission_id: UUID,
        granted_at: datetime,
    ) -> RolePermission:
        assignment = await self.session.get(
            RolePermission,
            {
                "role_id": role_id,
                "permission_id": permission_id,
            },
        )

        if assignment is None:
            assignment = RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                granted_at=granted_at,
            )
            self.session.add(assignment)
        else:
            assignment.granted_at = granted_at

        await self.session.flush()
        return assignment

    async def revoke_permission(
        self,
        *,
        role_id: UUID,
        permission_id: UUID,
    ) -> bool:
        statement = delete(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )

        result = await self.session.execute(statement)
        await self.session.flush()

        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount)

    async def get_access_snapshot(
        self,
        *,
        user_id: UUID,
        now: datetime,
    ) -> AccessSnapshot:
        active_assignment = or_(
            UserRole.expires_at.is_(None),
            UserRole.expires_at > now,
        )

        roles_statement = (
            select(Role.name)
            .join(
                UserRole,
                UserRole.role_id == Role.id,
            )
            .where(
                UserRole.user_id == user_id,
                active_assignment,
            )
            .distinct()
            .order_by(Role.name)
        )

        role_names_result = await self.session.scalars(roles_statement)
        role_names = frozenset(role_names_result.all())

        permissions_statement = (
            select(Permission.code)
            .join(
                RolePermission,
                RolePermission.permission_id == Permission.id,
            )
            .join(
                UserRole,
                UserRole.role_id == RolePermission.role_id,
            )
            .where(
                UserRole.user_id == user_id,
                active_assignment,
            )
            .distinct()
            .order_by(Permission.code)
        )

        permission_codes_result = await self.session.scalars(permissions_statement)
        permission_codes = frozenset(permission_codes_result.all())

        return AccessSnapshot(
            user_id=user_id,
            role_names=role_names,
            permission_codes=permission_codes,
        )
