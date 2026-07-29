from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import (
    Annotated,
    TypeAlias,
)

from app.core.security import AccessTokenClaims
from app.db.models.identity import AuthSession, User
from app.modules.auth.dependencies import (
    CurrentAccessTokenDependency,
    CurrentActiveUser,
    DatabaseSession,
)
from app.modules.rbac.repository import (
    AccessSnapshot,
    RBACRepository,
)
from fastapi import Depends, HTTPException, status
from fastapi.security import SecurityScopes


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    user: User
    auth_session: AuthSession
    claims: AccessTokenClaims
    roles: frozenset[str]
    permissions: frozenset[str]

    def has_role(
        self,
        role_name: str,
    ) -> bool:
        return role_name in self.roles

    def has_permission(
        self,
        permission_code: str,
    ) -> bool:
        return permission_code in self.permissions


async def get_authorization_context(
    current_access: CurrentAccessTokenDependency,
    current_active_user: CurrentActiveUser,
    session: DatabaseSession,
) -> AuthorizationContext:
    """
    Resolve the user's current roles and permissions from PostgreSQL.

    The permission list is deliberately not sourced from the JWT.
    """
    repository = RBACRepository(session)

    snapshot: AccessSnapshot = await repository.get_access_snapshot(
        user_id=current_active_user.id,
        now=datetime.now(UTC).replace(microsecond=0),
    )

    return AuthorizationContext(
        user=current_active_user,
        auth_session=current_access.auth_session,
        claims=current_access.claims,
        roles=snapshot.role_names,
        permissions=snapshot.permission_codes,
    )


CurrentAuthorization: TypeAlias = Annotated[
    AuthorizationContext,
    Depends(get_authorization_context),
]


async def require_permissions(
    security_scopes: SecurityScopes,
    authorization: CurrentAuthorization,
) -> AuthorizationContext:
    """
    Require every permission declared through Security(..., scopes=[]).

    This uses AND semantics.
    """
    required = frozenset(
        permission.strip() for permission in security_scopes.scopes if permission.strip()
    )

    missing = required.difference(authorization.permissions)

    if missing:
        raise _permission_denied(
            code="INSUFFICIENT_PERMISSIONS",
            message=(
                "The current account does not have all permissions required for this operation."
            ),
            required=sorted(required),
        )

    return authorization


AuthorizationDependency: TypeAlias = Callable[
    [AuthorizationContext],
    Awaitable[AuthorizationContext],
]


def require_permission(
    permission_code: str,
) -> AuthorizationDependency:
    """
    Dependency factory requiring one database permission.
    """
    normalized = permission_code.strip()

    if not normalized:
        raise ValueError("Permission code must not be empty")

    async def dependency(
        authorization: CurrentAuthorization,
    ) -> AuthorizationContext:
        if normalized not in authorization.permissions:
            raise _permission_denied(
                code="INSUFFICIENT_PERMISSION",
                message=("The current account does not have the required permission."),
                required=[normalized],
            )

        return authorization

    return dependency


def require_any_permission(
    *permission_codes: str,
) -> AuthorizationDependency:
    """
    Require at least one supplied database permission.

    This uses OR semantics.
    """
    normalized = tuple(
        dict.fromkeys(permission.strip() for permission in permission_codes if permission.strip())
    )

    if not normalized:
        raise ValueError("At least one permission is required")

    async def dependency(
        authorization: CurrentAuthorization,
    ) -> AuthorizationContext:
        if not any(permission in authorization.permissions for permission in normalized):
            raise _permission_denied(
                code="INSUFFICIENT_PERMISSIONS",
                message=(
                    "The current account does not have any accepted permission for this operation."
                ),
                required=list(normalized),
            )

        return authorization

    return dependency


def require_role(
    role_name: str,
) -> AuthorizationDependency:
    """
    Require one currently assigned database role.
    """
    normalized = role_name.strip().upper()

    if not normalized:
        raise ValueError("Role name must not be empty")

    async def dependency(
        authorization: CurrentAuthorization,
    ) -> AuthorizationContext:
        normalized_roles = {assigned_role.upper() for assigned_role in authorization.roles}

        if normalized not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "REQUIRED_ROLE_MISSING",
                    "message": ("The current account does not have the required role."),
                    "requiredRole": normalized,
                },
            )

        return authorization

    return dependency


def _permission_denied(
    *,
    code: str,
    message: str,
    required: list[str],
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": code,
            "message": message,
            "requiredPermissions": required,
        },
    )
