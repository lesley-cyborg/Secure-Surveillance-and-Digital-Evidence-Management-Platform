from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from jwt import ExpiredSignatureError
from jwt import InvalidTokenError as PyJWTInvalidTokenError
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import get_settings


class SecurityError(Exception):
    """Base exception for authentication security failures."""


class InvalidAccessTokenError(SecurityError):
    """Raised when an access token cannot be trusted."""


class ExpiredAccessTokenError(InvalidAccessTokenError):
    """Raised when an access token has expired."""


class AccessTokenClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sub: UUID
    sid: UUID
    jti: UUID
    typ: Literal["access"]

    iss: str
    aud: str

    iat: datetime
    nbf: datetime
    exp: datetime


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    token: str
    jti: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    token: str
    token_hash: str
    jti: UUID
    family_id: UUID
    expires_at: datetime


_password_hasher = PasswordHasher()


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using Argon2id.

    Request-schema validation will enforce the complete password policy,
    but this function still rejects empty values defensively.
    """
    if not password:
        raise ValueError("Password must not be empty")

    return _password_hasher.hash(password)


def verify_password(
    password: str,
    encoded_hash: str,
) -> bool:
    """
    Verify a password without exposing Argon2 exceptions to callers.
    """
    if not password or not encoded_hash:
        return False

    try:
        return _password_hasher.verify(
            encoded_hash,
            password,
        )
    except (
        VerifyMismatchError,
        VerificationError,
        InvalidHashError,
    ):
        return False


def password_needs_rehash(encoded_hash: str) -> bool:
    """
    Determine whether the stored password hash uses outdated parameters.
    """
    try:
        return _password_hasher.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return True


def create_access_token(
    *,
    user_id: UUID,
    session_id: UUID,
    now: datetime | None = None,
    expires_delta: timedelta | None = None,
) -> IssuedAccessToken:
    settings = get_settings()

    issued_at = now or utc_now()

    if issued_at.tzinfo is None:
        raise ValueError("Token timestamps must be timezone-aware")

    issued_at = issued_at.astimezone(UTC).replace(microsecond=0)

    lifetime = expires_delta or timedelta(minutes=settings.jwt_access_token_minutes)
    expires_at = issued_at + lifetime
    token_id = uuid4()

    payload: dict[str, object] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": str(token_id),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
    }

    encoded = jwt.encode(
        payload=payload,
        key=settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    return IssuedAccessToken(
        token=encoded,
        jti=token_id,
        expires_at=expires_at,
    )


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_settings()

    if not token:
        raise InvalidAccessTokenError("Access token is required")

    try:
        payload = jwt.decode(
            jwt=token,
            key=settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            leeway=settings.jwt_leeway_seconds,
            options={
                "require": [
                    "sub",
                    "sid",
                    "jti",
                    "typ",
                    "iss",
                    "aud",
                    "iat",
                    "nbf",
                    "exp",
                ],
            },
        )

        return AccessTokenClaims.model_validate(payload)

    except ExpiredSignatureError as exc:
        raise ExpiredAccessTokenError("Access token has expired") from exc

    except (
        PyJWTInvalidTokenError,
        ValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise InvalidAccessTokenError("Access token is invalid") from exc


def hash_refresh_token(token: str) -> str:
    if not token:
        raise ValueError("Refresh token must not be empty")

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_matches(
    presented_token: str,
    stored_token_hash: str,
) -> bool:
    if not presented_token or not stored_token_hash:
        return False

    presented_hash = hash_refresh_token(presented_token)

    return hmac.compare_digest(
        presented_hash,
        stored_token_hash,
    )


def create_refresh_token(
    *,
    family_id: UUID | None = None,
    now: datetime | None = None,
) -> IssuedRefreshToken:
    settings = get_settings()

    issued_at = now or utc_now()

    if issued_at.tzinfo is None:
        raise ValueError("Token timestamps must be timezone-aware")

    issued_at = issued_at.astimezone(UTC)
    expires_at = issued_at + timedelta(days=settings.jwt_refresh_token_days)

    plaintext_token = secrets.token_urlsafe(settings.refresh_token_bytes)

    return IssuedRefreshToken(
        token=plaintext_token,
        token_hash=hash_refresh_token(plaintext_token),
        jti=uuid4(),
        family_id=family_id or uuid4(),
        expires_at=expires_at,
    )
