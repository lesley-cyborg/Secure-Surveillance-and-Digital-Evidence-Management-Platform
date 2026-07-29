from __future__ import annotations

from datetime import UTC, datetime
from math import ceil
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis


class TokenRevocationStore(Protocol):
    async def revoke_access_token(
        self,
        *,
        jti: UUID,
        expires_at: datetime,
        now: datetime,
    ) -> None: ...

    async def revoke_session(
        self,
        session_id: UUID,
    ) -> None: ...

    async def revoke_sessions(
        self,
        session_ids: list[UUID],
    ) -> None: ...

    async def is_revoked(
        self,
        *,
        jti: UUID,
        session_id: UUID,
    ) -> bool: ...


class NullTokenRevocationStore:
    async def revoke_access_token(
        self,
        *,
        jti: UUID,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        del jti, expires_at, now

    async def revoke_session(
        self,
        session_id: UUID,
    ) -> None:
        del session_id

    async def revoke_sessions(
        self,
        session_ids: list[UUID],
    ) -> None:
        del session_ids

    async def is_revoked(
        self,
        *,
        jti: UUID,
        session_id: UUID,
    ) -> bool:
        del jti, session_id
        return False


class RedisTokenRevocationStore:
    access_prefix = "auth:revoked:access"
    session_prefix = "auth:revoked:session"

    def __init__(
        self,
        redis: Redis,
        *,
        session_ttl_seconds: int,
    ) -> None:
        self.redis = redis
        self.session_ttl_seconds = session_ttl_seconds

    def _access_key(self, jti: UUID) -> str:
        return f"{self.access_prefix}:{jti}"

    def _session_key(
        self,
        session_id: UUID,
    ) -> str:
        return f"{self.session_prefix}:{session_id}"

    async def revoke_access_token(
        self,
        *,
        jti: UUID,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        if expires_at.tzinfo is None:
            raise ValueError("Access-token expiry must be timezone-aware")

        if now.tzinfo is None:
            raise ValueError("Current time must be timezone-aware")

        remaining_seconds = ceil((expires_at.astimezone(UTC) - now.astimezone(UTC)).total_seconds())

        ttl = max(1, remaining_seconds)

        await self.redis.set(
            self._access_key(jti),
            "1",
            ex=ttl,
        )

    async def revoke_session(
        self,
        session_id: UUID,
    ) -> None:
        await self.redis.set(
            self._session_key(session_id),
            "1",
            ex=self.session_ttl_seconds,
        )

    async def revoke_sessions(
        self,
        session_ids: list[UUID],
    ) -> None:
        unique_ids = list(dict.fromkeys(session_ids))

        if not unique_ids:
            return

        pipeline = self.redis.pipeline(transaction=False)

        for session_id in unique_ids:
            pipeline.set(
                self._session_key(session_id),
                "1",
                ex=self.session_ttl_seconds,
            )

        await pipeline.execute()

    async def is_revoked(
        self,
        *,
        jti: UUID,
        session_id: UUID,
    ) -> bool:
        values = await self.redis.mget(
            self._access_key(jti),
            self._session_key(session_id),
        )

        return any(value is not None for value in values)
