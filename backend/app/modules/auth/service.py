from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.db.models.enums import AuditOutcome
from app.db.models.identity import User
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import AuditRepository
from app.modules.auth.exceptions import (
    AuthenticationRejectedError,
    MfaVerificationRejectedError,
    RefreshTokenRejectedError,
    RefreshTokenReuseDetectedError,
)
from app.modules.auth.mfa_store import (
    MfaChallenge,
    MfaChallengeIssuer,
)
from app.modules.auth.repository import (
    AuthSessionRepository,
    UserRepository,
)
from app.modules.auth.schemas import (
    AuthenticatedUser,
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    MfaChallengeResponse,
    MfaVerifyRequest,
    RefreshTokenRequest,
    TokenPair,
)
from app.modules.auth.token_store import (
    NullTokenRevocationStore,
    TokenRevocationStore,
)
from app.modules.rbac.repository import RBACRepository

logger = logging.getLogger(__name__)

# LOGIN_AUDIT_ACTION = "AUTH_LOGIN_ATTEMPT"
# ACCOUNT_LOCKED_ACTION = "AUTH_ACCOUNT_LOCKED"


@dataclass(frozen=True, slots=True)
class LoginContext:
    correlation_id: str
    source_ip: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class AccessSessionContext:
    user_id: UUID
    session_id: UUID
    access_token_jti: UUID
    access_token_expires_at: datetime

    correlation_id: str
    source_ip: str | None
    user_agent: str | None


type LoginResult = AuthResponse | MfaChallengeResponse


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """
    Produce one reusable Argon2 hash for unknown-account checks.

    This reduces the timing difference between a missing user and a
    known user with an invalid password.
    """
    return hash_password(secrets.token_urlsafe(48))


def _identifier_fingerprint(identifier: str) -> str:
    """
    Permit login-attempt correlation without writing the supplied
    email address or username into audit metadata.
    """
    normalized = identifier.strip().casefold()

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class AuthenticationService:
    def __init__(
        self,
        session: AsyncSession,
        mfa_challenges: MfaChallengeIssuer,
        revocations: TokenRevocationStore | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()

        self.users = UserRepository(session)
        self.sessions = AuthSessionRepository(session)
        self.rbac = RBACRepository(session)
        self.audit = AuditRepository(session)

        self.mfa_challenges = mfa_challenges
        self.revocations = revocations or NullTokenRevocationStore()

    async def login(
        self,
        payload: LoginRequest,
        context: LoginContext,
    ) -> LoginResult:
        now = _utc_now()
        password = payload.password.get_secret_value()
        fingerprint = _identifier_fingerprint(payload.identifier)

        issued_mfa_challenge: MfaChallenge | None = None

        try:
            user = await self.users.get_by_identifier_for_update(payload.identifier)

            if user is None:
                # Perform an Argon2 verification even when no user exists.
                verify_password(
                    password,
                    _dummy_password_hash(),
                )

                await self._audit_login(
                    user=None,
                    context=context,
                    now=now,
                    action=AuditAction.AUTH_LOGIN_FAILED,
                    outcome=AuditOutcome.FAILURE,
                    reason="user_not_found",
                    identifier_fingerprint=fingerprint,
                )

                await self.session.commit()

                raise AuthenticationRejectedError("user_not_found")

            if not user.is_active:
                await self._audit_login(
                    user=user,
                    context=context,
                    now=now,
                    action=AuditAction.AUTH_ACCOUNT_LOCKED,
                    outcome=AuditOutcome.DENIED,
                    reason="account_inactive",
                    identifier_fingerprint=fingerprint,
                )

                await self.session.commit()

                raise AuthenticationRejectedError("account_inactive")

            if user.locked_until is not None and user.locked_until > now:
                await self._audit_login(
                    user=user,
                    context=context,
                    now=now,
                    action=AuditAction.AUTH_LOGIN_FAILED,
                    outcome=AuditOutcome.DENIED,
                    reason="account_locked",
                    identifier_fingerprint=fingerprint,
                    additional_details={
                        "locked_until": (user.locked_until.isoformat()),
                    },
                )

                await self.session.commit()

                raise AuthenticationRejectedError("account_locked")

            # An expired lock should not make the next failed attempt
            # immediately re-lock the account.
            if user.locked_until is not None and user.locked_until <= now:
                await self.users.clear_failed_login_state(user)

            if not verify_password(
                password,
                user.password_hash,
            ):
                await self._handle_invalid_password(
                    user=user,
                    context=context,
                    now=now,
                    identifier_fingerprint=fingerprint,
                )

                await self.session.commit()

                raise AuthenticationRejectedError("invalid_password")

            password_rehashed = False

            if password_needs_rehash(user.password_hash):
                await self.users.update_password_hash(
                    user,
                    hash_password(password),
                )
                password_rehashed = True

            # Primary credentials are correct, but authentication is
            # not complete until MFA succeeds.
            if user.mfa_enabled:
                await self.users.clear_failed_login_state(user)

                mfa_challenge = await self.mfa_challenges.issue(
                    user_id=user.id,
                    correlation_id=(context.correlation_id),
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    now=now,
                )

                # Keep this reference so the challenge can be deleted
                # if a later database operation fails.
                issued_mfa_challenge = mfa_challenge

                await self._audit_login(
                    user=user,
                    context=context,
                    now=now,
                    action=(AuditAction.AUTH_MFA_CHALLENGE_ISSUED),
                    outcome=AuditOutcome.SUCCESS,
                    reason="mfa_required",
                    identifier_fingerprint=fingerprint,
                    additional_details={
                        "challenge_id": str(mfa_challenge.id),
                        "password_rehashed": (password_rehashed),
                    },
                )

                mfa_response = MfaChallengeResponse(
                    challenge_id=mfa_challenge.id,
                    expires_at=mfa_challenge.expires_at,
                )

                await self.session.commit()
                return mfa_response

            refresh_token = create_refresh_token(now=now)

            auth_session = await self.sessions.create(
                user_id=user.id,
                refresh_token_hash=(refresh_token.token_hash),
                token_jti=refresh_token.jti,
                expires_at=refresh_token.expires_at,
                ip_address=context.source_ip,
                user_agent=context.user_agent,
            )

            access_token = create_access_token(
                user_id=user.id,
                session_id=auth_session.id,
                now=now,
            )

            access_snapshot = await self.rbac.get_access_snapshot(
                user_id=user.id,
                now=now,
            )

            await self.users.record_successful_login(
                user,
                logged_in_at=now,
            )

            await self._audit_login(
                user=user,
                context=context,
                now=now,
                action=AuditAction.AUTH_LOGIN_SUCCEEDED,
                outcome=AuditOutcome.SUCCESS,
                reason="authenticated",
                identifier_fingerprint=fingerprint,
                additional_details={
                    "session_id": str(auth_session.id),
                    "access_token_jti": str(access_token.jti),
                    "refresh_token_jti": str(refresh_token.jti),
                    "roles": sorted(access_snapshot.role_names),
                    "permission_count": len(access_snapshot.permission_codes),
                    "password_rehashed": (password_rehashed),
                },
            )

            auth_response = AuthResponse(
                user=AuthenticatedUser(
                    id=user.id,
                    email=user.email,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    mfa_enabled=user.mfa_enabled,
                    roles=sorted(access_snapshot.role_names),
                    permissions=sorted(access_snapshot.permission_codes),
                ),
                tokens=TokenPair(
                    access_token=access_token.token,
                    refresh_token=refresh_token.token,
                    access_token_expires_at=(access_token.expires_at),
                    refresh_token_expires_at=(refresh_token.expires_at),
                ),
            )

            await self.session.commit()
            return auth_response

        except AuthenticationRejectedError:
            # Rejection state and audit event were deliberately
            # committed before raising this domain exception.
            raise

        except Exception:
            await self.session.rollback()

            if issued_mfa_challenge is not None:
                await self.mfa_challenges.delete(issued_mfa_challenge.id)

            raise

    async def _handle_invalid_password(
        self,
        *,
        user: User,
        context: LoginContext,
        now: datetime,
        identifier_fingerprint: str,
    ) -> None:
        next_attempt_count = user.failed_login_attempts + 1

        locked_until: datetime | None = None

        if next_attempt_count >= self.settings.auth_max_failed_attempts:
            locked_until = now + timedelta(minutes=(self.settings.auth_lockout_minutes))

        await self.users.record_failed_login(
            user,
            locked_until=locked_until,
        )

        await self._audit_login(
            user=user,
            context=context,
            now=now,
            action=AuditAction.AUTH_LOGIN_FAILED,
            outcome=AuditOutcome.FAILURE,
            reason="invalid_password",
            identifier_fingerprint=(identifier_fingerprint),
            additional_details={
                "failed_login_attempts": (next_attempt_count),
                "account_locked": (locked_until is not None),
            },
        )

        if locked_until is not None:
            await self.audit.create(
                actor_user_id=user.id,
                action=(AuditAction.AUTH_ACCOUNT_LOCKED),
                resource_type="user",
                resource_id=user.id,
                outcome=AuditOutcome.DENIED,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                correlation_id=(context.correlation_id),
                details={
                    "locked_until": (locked_until.isoformat()),
                    "failed_login_attempts": (next_attempt_count),
                },
                occurred_at=now,
            )

    async def _audit_login(
        self,
        *,
        user: User | None,
        context: LoginContext,
        now: datetime,
        action: AuditAction,
        outcome: AuditOutcome,
        reason: str,
        identifier_fingerprint: str,
        additional_details: (dict[str, object] | None) = None,
    ) -> None:
        details: dict[str, object] = {
            "reason": reason,
            "identifier_fingerprint": (identifier_fingerprint),
        }

        if additional_details:
            details.update(additional_details)

        await self.audit.create(
            actor_user_id=(user.id if user is not None else None),
            action=action,
            resource_type="user",
            resource_id=(user.id if user is not None else None),
            outcome=outcome,
            source_ip=context.source_ip,
            user_agent=context.user_agent,
            correlation_id=context.correlation_id,
            details=details,
            occurred_at=now,
        )

    async def verify_mfa(
        self,
        payload: MfaVerifyRequest,
        context: LoginContext,
    ) -> AuthResponse:
        now = _utc_now()

        try:
            challenge = await self.mfa_challenges.consume(
                challenge_id=payload.challenge_id,
                submitted_code=(payload.code.get_secret_value()),
                now=now,
            )

            if challenge is None:
                await self.audit.create(
                    actor_user_id=None,
                    action=(AuditAction.AUTH_MFA_VERIFICATION_FAILED),
                    resource_type="mfa_challenge",
                    resource_id=payload.challenge_id,
                    outcome=AuditOutcome.FAILURE,
                    correlation_id=(context.correlation_id),
                    occurred_at=now,
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    details={
                        "reason": ("invalid_or_expired_challenge"),
                    },
                )

                await self.session.commit()

                raise MfaVerificationRejectedError("invalid_or_expired_challenge")

            user = await self.users.get_by_id_for_update(
                challenge.user_id,
                include_deleted=True,
            )

            if (
                user is None
                or user.deleted_at is not None
                or not user.is_active
                or not user.mfa_enabled
            ):
                await self.audit.create(
                    actor_user_id=(challenge.user_id),
                    action=(AuditAction.AUTH_MFA_VERIFICATION_FAILED),
                    resource_type="mfa_challenge",
                    resource_id=challenge.id,
                    outcome=AuditOutcome.DENIED,
                    correlation_id=(context.correlation_id),
                    occurred_at=now,
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    details={
                        "reason": "account_unavailable",
                    },
                )

                await self.session.commit()

                raise MfaVerificationRejectedError("account_unavailable")

            refresh_token = create_refresh_token(now=now)

            auth_session = await self.sessions.create(
                user_id=user.id,
                refresh_token_hash=(refresh_token.token_hash),
                token_jti=refresh_token.jti,
                expires_at=refresh_token.expires_at,
                ip_address=context.source_ip,
                user_agent=context.user_agent,
            )

            access_token = create_access_token(
                user_id=user.id,
                session_id=auth_session.id,
                now=now,
            )

            access_snapshot = await self.rbac.get_access_snapshot(
                user_id=user.id,
                now=now,
            )

            await self.users.record_successful_login(
                user,
                logged_in_at=now,
            )

            await self.audit.create(
                actor_user_id=user.id,
                action=(AuditAction.AUTH_MFA_VERIFICATION_SUCCEEDED),
                resource_type="mfa_challenge",
                resource_id=challenge.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=context.correlation_id,
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "session_id": str(auth_session.id),
                    "access_token_jti": str(access_token.jti),
                },
            )

            await self.audit.create(
                actor_user_id=user.id,
                action=AuditAction.AUTH_LOGIN_SUCCEEDED,
                resource_type="user",
                resource_id=user.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=context.correlation_id,
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "authentication_method": ("password_and_mfa"),
                    "session_id": str(auth_session.id),
                    "permission_count": len(access_snapshot.permission_codes),
                },
            )

            response = AuthResponse(
                user=AuthenticatedUser(
                    id=user.id,
                    email=user.email,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    mfa_enabled=user.mfa_enabled,
                    roles=sorted(access_snapshot.role_names),
                    permissions=sorted(access_snapshot.permission_codes),
                ),
                tokens=TokenPair(
                    access_token=access_token.token,
                    refresh_token=refresh_token.token,
                    access_token_expires_at=(access_token.expires_at),
                    refresh_token_expires_at=(refresh_token.expires_at),
                ),
            )

            await self.session.commit()

            return response

        except MfaVerificationRejectedError:
            raise

        except Exception:
            await self.session.rollback()
            raise

    async def refresh(
        self,
        payload: RefreshTokenRequest,
        context: LoginContext,
    ) -> TokenPair:
        now = _utc_now()

        plaintext_token = payload.refresh_token.get_secret_value()
        token_hash = hash_refresh_token(plaintext_token)

        try:
            # First lookup identifies which user row must be
            # locked. Security decisions are not made from
            # this unlocked result.
            candidate = await self.sessions.get_by_refresh_hash(token_hash)

            if candidate is None:
                await self.audit.create(
                    action=AuditAction.AUTH_TOKEN_REFRESHED,
                    resource_type="auth_session",
                    outcome=AuditOutcome.FAILURE,
                    correlation_id=context.correlation_id,
                    occurred_at=now,
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    details={
                        "reason": "refresh_token_not_found",
                    },
                )

                await self.session.commit()

                raise RefreshTokenRejectedError("refresh_token_not_found")

            user = await self.users.get_by_id_for_update(
                candidate.user_id,
                include_deleted=True,
            )

            current_session = await self.sessions.get_by_refresh_hash_for_update(token_hash)

            if current_session is None:
                await self.session.rollback()
                raise RefreshTokenRejectedError("refresh_session_disappeared")

            # A replacement link proves this token was
            # already successfully rotated.
            if current_session.replaced_by_session_id is not None:
                revoked_ids = await self.sessions.revoke_replacement_chain(
                    starting_session_id=(current_session.id),
                    revoked_at=now,
                )

                await self.audit.create(
                    actor_user_id=current_session.user_id,
                    action=(AuditAction.AUTH_REFRESH_REUSE_DETECTED),
                    resource_type="auth_session",
                    resource_id=current_session.id,
                    outcome=AuditOutcome.DENIED,
                    correlation_id=context.correlation_id,
                    occurred_at=now,
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    details={
                        "reason": ("rotated_refresh_token_reused"),
                        "revoked_session_ids": [str(session_id) for session_id in revoked_ids],
                    },
                )

                await self.session.commit()

                await self._mark_sessions_revoked(revoked_ids)

                raise RefreshTokenReuseDetectedError("rotated_refresh_token_reused")

            if current_session.revoked_at is not None:
                await self.audit.create(
                    actor_user_id=current_session.user_id,
                    action=AuditAction.AUTH_TOKEN_REFRESHED,
                    resource_type="auth_session",
                    resource_id=current_session.id,
                    outcome=AuditOutcome.DENIED,
                    correlation_id=context.correlation_id,
                    occurred_at=now,
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    details={
                        "reason": "refresh_session_revoked",
                    },
                )

                await self.session.commit()

                raise RefreshTokenRejectedError("refresh_session_revoked")

            if current_session.expires_at <= now:
                await self.sessions.revoke(
                    current_session,
                    revoked_at=now,
                )

                await self.audit.create(
                    actor_user_id=current_session.user_id,
                    action=AuditAction.AUTH_TOKEN_REFRESHED,
                    resource_type="auth_session",
                    resource_id=current_session.id,
                    outcome=AuditOutcome.FAILURE,
                    correlation_id=context.correlation_id,
                    occurred_at=now,
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    details={
                        "reason": "refresh_token_expired",
                    },
                )

                await self.session.commit()

                await self._mark_sessions_revoked([current_session.id])

                raise RefreshTokenRejectedError("refresh_token_expired")

            if user is None or user.deleted_at is not None or not user.is_active:
                revoked_ids = await self.sessions.revoke_all_active_for_user(
                    current_session.user_id,
                    revoked_at=now,
                )

                await self.audit.create(
                    actor_user_id=current_session.user_id,
                    action=AuditAction.AUTH_TOKEN_REFRESHED,
                    resource_type="auth_session",
                    resource_id=current_session.id,
                    outcome=AuditOutcome.DENIED,
                    correlation_id=context.correlation_id,
                    occurred_at=now,
                    source_ip=context.source_ip,
                    user_agent=context.user_agent,
                    details={
                        "reason": "account_unavailable",
                    },
                )

                await self.session.commit()

                await self._mark_sessions_revoked(revoked_ids)

                raise RefreshTokenRejectedError("account_unavailable")

            replacement_token = create_refresh_token(now=now)

            replacement_session = await self.sessions.rotate(
                current_session=current_session,
                new_refresh_token_hash=(replacement_token.token_hash),
                new_token_jti=(replacement_token.jti),
                new_expires_at=(replacement_token.expires_at),
                rotated_at=now,
                ip_address=context.source_ip,
                user_agent=context.user_agent,
            )

            access_token = create_access_token(
                user_id=user.id,
                session_id=replacement_session.id,
                now=now,
            )

            await self.audit.create(
                actor_user_id=user.id,
                action=AuditAction.AUTH_TOKEN_REFRESHED,
                resource_type="auth_session",
                resource_id=replacement_session.id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=context.correlation_id,
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "previous_session_id": str(current_session.id),
                    "replacement_session_id": str(replacement_session.id),
                    "access_token_jti": str(access_token.jti),
                    "refresh_token_jti": str(replacement_token.jti),
                },
            )

            response = TokenPair(
                access_token=access_token.token,
                refresh_token=replacement_token.token,
                access_token_expires_at=(access_token.expires_at),
                refresh_token_expires_at=(replacement_token.expires_at),
            )

            await self.session.commit()

            # The old database session is already revoked,
            # so this Redis update is a fast invalidation layer.
            await self._mark_sessions_revoked([current_session.id])

            return response

        except RefreshTokenRejectedError:
            raise

        except Exception:
            await self.session.rollback()
            raise

    async def _mark_sessions_revoked(
        self,
        session_ids: list[UUID],
    ) -> None:
        try:
            await self.revocations.revoke_sessions(session_ids)
        except RedisError:
            logger.exception("Could not write session revocations to Redis")

    async def _mark_access_token_revoked(
        self,
        *,
        context: AccessSessionContext,
    ) -> None:
        try:
            await self.revocations.revoke_access_token(
                jti=context.access_token_jti,
                expires_at=context.access_token_expires_at,
                now=_utc_now(),
            )
        except RedisError:
            logger.exception("Could not blacklist access-token JTI")

    async def logout(
        self,
        payload: LogoutRequest | None,
        context: AccessSessionContext,
    ) -> None:
        now = _utc_now()
        request = payload or LogoutRequest()

        try:
            user = await self.users.get_by_id_for_update(
                context.user_id,
                include_deleted=True,
            )

            if user is None:
                raise AuthenticationRejectedError("user_not_found")

            requested_session_id = context.session_id

            if request.refresh_token is not None:
                token_hash = hash_refresh_token(request.refresh_token.get_secret_value())

                candidate = await self.sessions.get_by_refresh_hash(token_hash)

                if candidate is None or candidate.user_id != context.user_id:
                    await self.audit.create(
                        actor_user_id=context.user_id,
                        action="AUTH_LOGOUT",
                        resource_type="auth_session",
                        resource_id=context.session_id,
                        outcome=AuditOutcome.DENIED,
                        correlation_id=(context.correlation_id),
                        occurred_at=now,
                        source_ip=context.source_ip,
                        user_agent=context.user_agent,
                        details={
                            "reason": ("refresh_token_mismatch"),
                        },
                    )

                    await self.session.commit()

                    raise RefreshTokenRejectedError("refresh_token_mismatch")

                requested_session_id = candidate.id

            revoked_session_ids: list[UUID]

            if request.all_sessions:
                revoked_session_ids = await self.sessions.revoke_all_active_for_user(
                    context.user_id,
                    revoked_at=now,
                )
                audit_action = "AUTH_LOGOUT_ALL"
            else:
                target_session = await self.sessions.get_by_id_for_update(requested_session_id)

                if target_session is not None and target_session.user_id != context.user_id:
                    raise RefreshTokenRejectedError("session_owner_mismatch")

                revoked_session_ids = []

                if target_session is not None:
                    await self.sessions.revoke(
                        target_session,
                        revoked_at=now,
                    )
                    revoked_session_ids.append(target_session.id)

                audit_action = "AUTH_LOGOUT"

            await self.audit.create(
                actor_user_id=context.user_id,
                action=audit_action,
                resource_type="auth_session",
                resource_id=context.session_id,
                outcome=AuditOutcome.SUCCESS,
                correlation_id=context.correlation_id,
                occurred_at=now,
                source_ip=context.source_ip,
                user_agent=context.user_agent,
                details={
                    "all_sessions": request.all_sessions,
                    "revoked_session_ids": [str(session_id) for session_id in revoked_session_ids],
                },
            )

            await self.session.commit()

            await self._mark_access_token_revoked(
                context=context,
            )

            await self._mark_sessions_revoked(
                list(
                    {
                        *revoked_session_ids,
                        context.session_id,
                    }
                )
            )

        except (
            AuthenticationRejectedError,
            RefreshTokenRejectedError,
        ):
            raise

        except Exception:
            await self.session.rollback()
            raise
