from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol, TypedDict, cast
from uuid import UUID, uuid4

from redis.asyncio import Redis
from redis.exceptions import WatchError

from app.core.config import get_settings


class _StoredMfaPayload(TypedDict):
    user_id: str
    correlation_id: str
    source_ip: str | None
    user_agent: str | None
    issued_at: str
    expires_at: str
    code_digest: str
    failed_attempts: int


@dataclass(frozen=True, slots=True)
class MfaChallenge:
    """
    A validated MFA challenge.

    This object never exposes the verification code.
    """

    id: UUID
    user_id: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedMfaChallenge(MfaChallenge):
    """
    Newly issued challenge.

    delivery_code must be passed to an email, SMS or authenticator
    delivery component. It must never be returned by the login API.
    """

    delivery_code: str = field(
        repr=False,
        compare=False,
    )


class MfaChallengeIssuer(Protocol):
    async def issue(
        self,
        *,
        user_id: UUID,
        correlation_id: str,
        source_ip: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> IssuedMfaChallenge: ...

    async def consume(
        self,
        *,
        challenge_id: UUID,
        submitted_code: str,
        now: datetime,
    ) -> MfaChallenge | None: ...

    async def delete(
        self,
        challenge_id: UUID,
    ) -> None: ...


class RedisMfaChallengeStore:
    key_prefix = "auth:mfa:challenge"

    def __init__(
        self,
        redis: Redis,
        *,
        ttl_minutes: int,
        maximum_attempts: int = 5,
        code_pepper: str | None = None,
    ) -> None:
        if ttl_minutes <= 0:
            raise ValueError("MFA challenge TTL must be positive")

        if maximum_attempts <= 0:
            raise ValueError("MFA maximum attempts must be positive")

        settings = get_settings()

        pepper = (
            code_pepper if code_pepper is not None else settings.jwt_secret_key.get_secret_value()
        )

        if not pepper:
            raise ValueError("MFA code pepper must not be empty")

        self.redis = redis
        self.ttl = timedelta(minutes=ttl_minutes)
        self.maximum_attempts = maximum_attempts
        self._code_pepper = pepper.encode("utf-8")

    def _key(
        self,
        challenge_id: UUID,
    ) -> str:
        return f"{self.key_prefix}:{challenge_id}"

    def _generate_code(self) -> str:
        """
        Generate a cryptographically secure six-digit code.
        """
        return f"{secrets.randbelow(1_000_000):06d}"

    def _digest_code(
        self,
        code: str,
    ) -> str:
        """
        Create an HMAC digest.

        HMAC is preferable to plain SHA-256 because MFA codes have a
        very small search space.
        """
        return hmac.new(
            self._code_pepper,
            code.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _serialize(
        payload: _StoredMfaPayload,
    ) -> str:
        return json.dumps(
            payload,
            separators=(",", ":"),
        )

    @staticmethod
    def _deserialize(
        raw_payload: bytes | str,
    ) -> _StoredMfaPayload:
        text = raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else raw_payload

        parsed = json.loads(text)

        if not isinstance(parsed, dict):
            raise ValueError("Invalid MFA challenge payload")

        return cast(
            _StoredMfaPayload,
            parsed,
        )

    async def issue(
        self,
        *,
        user_id: UUID,
        correlation_id: str,
        source_ip: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> IssuedMfaChallenge:
        if now.tzinfo is None:
            raise ValueError("MFA timestamp must be timezone-aware")

        issued_at = now.astimezone(UTC).replace(microsecond=0)
        expires_at = issued_at + self.ttl

        challenge_id = uuid4()
        delivery_code = self._generate_code()

        payload: _StoredMfaPayload = {
            "user_id": str(user_id),
            "correlation_id": (correlation_id[:64]),
            "source_ip": source_ip,
            "user_agent": (user_agent[:4096] if user_agent is not None else None),
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "code_digest": self._digest_code(delivery_code),
            "failed_attempts": 0,
        }

        created = await self.redis.set(
            self._key(challenge_id),
            self._serialize(payload),
            ex=max(
                1,
                int(self.ttl.total_seconds()),
            ),
            nx=True,
        )

        if not created:
            raise RuntimeError("Could not create MFA challenge")

        return IssuedMfaChallenge(
            id=challenge_id,
            user_id=user_id,
            expires_at=expires_at,
            delivery_code=delivery_code,
        )

    async def consume(
        self,
        *,
        challenge_id: UUID,
        submitted_code: str,
        now: datetime,
    ) -> MfaChallenge | None:
        """
        Verify and consume an MFA challenge.

        The Redis WATCH transaction guarantees that only one concurrent
        request can successfully consume the challenge.

        Invalid attempts increment a counter. The challenge is deleted
        when the maximum attempt limit is reached.
        """
        if now.tzinfo is None:
            raise ValueError("MFA timestamp must be timezone-aware")

        normalized_now = now.astimezone(UTC).replace(microsecond=0)
        key = self._key(challenge_id)

        submitted_digest = self._digest_code(submitted_code)

        # A WatchError means another request changed the challenge
        # between our read and write. Retry with the new value.
        for _ in range(5):
            async with self.redis.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(key)

                    raw_payload = await pipeline.get(key)

                    if raw_payload is None:
                        return None

                    try:
                        payload = self._deserialize(raw_payload)

                        user_id = UUID(payload["user_id"])
                        expires_at = datetime.fromisoformat(payload["expires_at"])

                        if expires_at.tzinfo is None:
                            raise ValueError("Stored MFA expiration must be timezone-aware")

                        expires_at = expires_at.astimezone(UTC).replace(microsecond=0)

                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ):
                        pipeline.multi()  # type: ignore[no-untyped-call]
                        pipeline.delete(key)
                        await pipeline.execute()
                        return None

                    if expires_at <= normalized_now:
                        pipeline.multi()  # type: ignore[no-untyped-call]
                        pipeline.delete(key)
                        await pipeline.execute()
                        return None

                    stored_digest = payload["code_digest"]

                    code_valid = hmac.compare_digest(
                        submitted_digest,
                        stored_digest,
                    )

                    if code_valid:
                        pipeline.multi()  # type: ignore[no-untyped-call]
                        pipeline.delete(key)
                        await pipeline.execute()

                        return MfaChallenge(
                            id=challenge_id,
                            user_id=user_id,
                            expires_at=expires_at,
                        )

                    failed_attempts = (
                        int(
                            payload.get(
                                "failed_attempts",
                                0,
                            )
                        )
                        + 1
                    )

                    pipeline.multi()  # type: ignore[no-untyped-call]

                    if failed_attempts >= self.maximum_attempts:
                        pipeline.delete(key)

                    else:
                        payload["failed_attempts"] = failed_attempts

                        remaining_seconds = max(
                            1,
                            int((expires_at - normalized_now).total_seconds()),
                        )

                        pipeline.set(
                            key,
                            self._serialize(payload),
                            ex=remaining_seconds,
                            xx=True,
                        )

                    await pipeline.execute()

                    return None

                except WatchError:
                    continue

        raise RuntimeError("Could not atomically consume the MFA challenge")

    async def delete(
        self,
        challenge_id: UUID,
    ) -> None:
        await self.redis.delete(self._key(challenge_id))
