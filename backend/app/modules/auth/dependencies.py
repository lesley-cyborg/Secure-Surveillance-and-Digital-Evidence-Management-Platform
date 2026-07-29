from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, TypeAlias, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    AccessTokenClaims,
    InvalidAccessTokenError,
    decode_access_token,
)
from app.db.models.identity import AuthSession, User
from app.db.session import get_db_session
from app.modules.auth.mfa_store import RedisMfaChallengeStore
from app.modules.auth.repository import (
    AuthSessionRepository,
    UserRepository,
)
from app.modules.auth.service import AuthenticationService
from app.modules.auth.token_store import (
    RedisTokenRevocationStore,
)

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(
    auto_error=False,
)


DatabaseSession: TypeAlias = Annotated[
    AsyncSession,
    Depends(get_db_session),
]


@dataclass(frozen=True, slots=True)
class CurrentSession:
    claims: AccessTokenClaims
    auth_session: AuthSession


@dataclass(frozen=True, slots=True)
class CurrentAccessToken:
    claims: AccessTokenClaims
    user: User
    auth_session: AuthSession


def get_token_revocation_store(
    request: Request,
) -> RedisTokenRevocationStore:
    settings = get_settings()

    redis = cast(
        Redis,
        request.app.state.redis,
    )

    session_ttl_seconds = settings.jwt_access_token_minutes * 60 + settings.jwt_leeway_seconds + 10

    return RedisTokenRevocationStore(
        redis,
        session_ttl_seconds=session_ttl_seconds,
    )


RevocationStoreDependency: TypeAlias = Annotated[
    RedisTokenRevocationStore,
    Depends(get_token_revocation_store),
]


def get_authentication_service(
    request: Request,
    session: DatabaseSession,
    revocations: RevocationStoreDependency,
) -> AuthenticationService:
    settings = get_settings()

    redis = cast(
        Redis,
        request.app.state.redis,
    )

    mfa_store = RedisMfaChallengeStore(
        redis,
        ttl_minutes=(settings.auth_mfa_challenge_minutes),
    )

    return AuthenticationService(
        session=session,
        mfa_challenges=mfa_store,
        revocations=revocations,
    )


AuthenticationServiceDependency: TypeAlias = Annotated[
    AuthenticationService,
    Depends(get_authentication_service),
]


async def get_current_session(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: DatabaseSession,
    revocations: RevocationStoreDependency,
) -> CurrentSession:
    """
    Validate the JWT and its corresponding database session.

    PostgreSQL remains authoritative. Redis provides fast revocation
    rejection but a Redis failure falls back to the database check.
    """
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()

    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise _unauthorized() from exc

    try:
        is_revoked = await revocations.is_revoked(
            jti=claims.jti,
            session_id=claims.sid,
        )
    except RedisError:
        logger.exception("Redis token-revocation lookup failed")
        is_revoked = False

    if is_revoked:
        raise _unauthorized()

    now = datetime.now(UTC).replace(microsecond=0)

    repository = AuthSessionRepository(session)

    auth_session = await repository.get_active_by_id(
        claims.sid,
        now=now,
    )

    if auth_session is None:
        raise _unauthorized()

    if auth_session.user_id != claims.sub:
        raise _unauthorized()

    return CurrentSession(
        claims=claims,
        auth_session=auth_session,
    )


CurrentSessionDependency: TypeAlias = Annotated[
    CurrentSession,
    Depends(get_current_session),
]


async def get_current_user(
    current_session: CurrentSessionDependency,
    session: DatabaseSession,
) -> User:
    """
    Load the JWT subject from PostgreSQL.

    This dependency guarantees that the user exists and has not been
    soft-deleted, but it does not require is_active=True.
    """
    repository = UserRepository(session)

    user = await repository.get_by_id(current_session.claims.sub)

    if user is None:
        raise _unauthorized()

    return user


CurrentUser: TypeAlias = Annotated[
    User,
    Depends(get_current_user),
]


async def get_current_active_user(
    current_user: CurrentUser,
) -> User:
    """
    Require an existing and active user account.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_INACTIVE",
                "message": ("This account is not permitted to access the platform."),
            },
        )

    return current_user


CurrentActiveUser: TypeAlias = Annotated[
    User,
    Depends(get_current_active_user),
]


async def get_current_access_token(
    current_session: CurrentSessionDependency,
    current_user: CurrentUser,
) -> CurrentAccessToken:
    """
    Compatibility dependency used by logout and token lifecycle routes.

    Inactive users can still reach logout so that their server-side
    session can be revoked.
    """
    return CurrentAccessToken(
        claims=current_session.claims,
        user=current_user,
        auth_session=current_session.auth_session,
    )


CurrentAccessTokenDependency: TypeAlias = Annotated[
    CurrentAccessToken,
    Depends(get_current_access_token),
]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "INVALID_ACCESS_TOKEN",
            "message": ("Authentication credentials are invalid or expired."),
        },
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )
