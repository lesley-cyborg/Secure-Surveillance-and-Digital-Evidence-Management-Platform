from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import AuthSession, User


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def normalize_username(username: str) -> str:
    return username.strip().casefold()


class UserRepository:
    """
    Persistence operations for users and authentication state.

    Repositories flush changes but never commit. Transaction boundaries
    normally belong to AuthenticationService.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def create(
        self,
        *,
        email: str,
        username: str,
        password_hash: str,
        first_name: str,
        last_name: str,
        phone: str | None = None,
        is_active: bool = True,
    ) -> User:
        user = User(
            email=normalize_email(email),
            username=normalize_username(username),
            password_hash=password_hash,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone=phone.strip() if phone else None,
            is_active=is_active,
        )

        self.session.add(user)
        await self.session.flush()

        return user

    async def get_by_email(
        self,
        email: str,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        statement = select(User).where(
            func.lower(User.email)
            == normalize_email(email)
        )

        if not include_deleted:
            statement = statement.where(
                User.deleted_at.is_(None)
            )

        result = await self.session.execute(
            statement
        )

        return result.scalar_one_or_none()

    async def get_by_username(
        self,
        username: str,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        statement = select(User).where(
            func.lower(User.username)
            == normalize_username(username)
        )

        if not include_deleted:
            statement = statement.where(
                User.deleted_at.is_(None)
            )

        result = await self.session.execute(
            statement
        )

        return result.scalar_one_or_none()

    async def list_users(
        self,
        *,
        offset: int,
        limit: int,
        include_deleted: bool = False,
    ) -> list[User]:
        statement = (
            select(User)
            .order_by(
                User.created_at.desc(),
                User.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        if not include_deleted:
            statement = statement.where(
                User.deleted_at.is_(None)
            )

        result = await self.session.scalars(
            statement
        )

        return list(result.all())

    async def count_users(
        self,
        *,
        include_deleted: bool = False,
    ) -> int:
        statement = select(
            func.count(User.id)
        )

        if not include_deleted:
            statement = statement.where(
                User.deleted_at.is_(None)
            )

        result = await self.session.scalar(
            statement
        )

        return int(result or 0)

    async def get_by_id(
        self,
        user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        statement = select(User).where(User.id == user_id)

        if not include_deleted:
            statement = statement.where(User.deleted_at.is_(None))

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self,
        user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        statement = select(User).where(User.id == user_id).with_for_update()

        if not include_deleted:
            statement = statement.where(User.deleted_at.is_(None))

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_identifier(
        self,
        identifier: str,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        normalized = identifier.strip().casefold()

        if "@" in normalized:
            condition = func.lower(User.email) == normalized
        else:
            condition = func.lower(User.username) == normalized

        statement = select(User).where(condition)

        if not include_deleted:
            statement = statement.where(User.deleted_at.is_(None))

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_identifier_for_update(
        self,
        identifier: str,
    ) -> User | None:
        normalized = identifier.strip().casefold()

        if "@" in normalized:
            condition = func.lower(User.email) == normalized
        else:
            condition = func.lower(User.username) == normalized

        statement = (
            select(User)
            .where(
                condition,
                User.deleted_at.is_(None),
            )
            .with_for_update()
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def update_password_hash(
        self,
        user: User,
        password_hash: str,
    ) -> None:
        user.password_hash = password_hash
        await self.session.flush()

    async def record_failed_login(
        self,
        user: User,
        *,
        locked_until: datetime | None,
    ) -> None:
        user.failed_login_attempts += 1
        user.locked_until = locked_until

        await self.session.flush()

    async def clear_failed_login_state(
        self,
        user: User,
    ) -> None:
        user.failed_login_attempts = 0
        user.locked_until = None

        await self.session.flush()

    async def record_successful_login(
        self,
        user: User,
        *,
        logged_in_at: datetime,
    ) -> None:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = logged_in_at

        await self.session.flush()

    async def set_active_status(
        self,
        user: User,
        *,
        is_active: bool,
    ) -> None:
        user.is_active = is_active
        await self.session.flush()


class AuthSessionRepository:
    """
    Persistence operations for refresh-token sessions.

    Only refresh-token hashes are stored.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: UUID,
        refresh_token_hash: str,
        token_jti: UUID | str,
        expires_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuthSession:
        auth_session = AuthSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            token_jti=str(token_jti),
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.session.add(auth_session)
        await self.session.flush()

        return auth_session

    async def get_by_id(
        self,
        session_id: UUID,
    ) -> AuthSession | None:
        return await self.session.get(
            AuthSession,
            session_id,
        )

    async def get_by_id_for_update(
        self,
        session_id: UUID,
    ) -> AuthSession | None:
        statement = select(AuthSession).where(AuthSession.id == session_id).with_for_update()

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_active_by_id(
        self,
        session_id: UUID,
        *,
        now: datetime,
    ) -> AuthSession | None:
        statement = select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_refresh_hash(
        self,
        refresh_token_hash: str,
    ) -> AuthSession | None:
        statement = select(AuthSession).where(AuthSession.refresh_token_hash == refresh_token_hash)

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_refresh_hash_for_update(
        self,
        refresh_token_hash: str,
    ) -> AuthSession | None:
        statement = (
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == refresh_token_hash)
            .with_for_update()
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def rotate(
        self,
        *,
        current_session: AuthSession,
        new_refresh_token_hash: str,
        new_token_jti: UUID | str,
        new_expires_at: datetime,
        rotated_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuthSession:
        replacement = AuthSession(
            user_id=current_session.user_id,
            refresh_token_hash=new_refresh_token_hash,
            token_jti=str(new_token_jti),
            expires_at=new_expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.session.add(replacement)
        await self.session.flush()

        current_session.revoked_at = rotated_at
        current_session.replaced_by_session_id = replacement.id

        await self.session.flush()

        return replacement

    async def revoke(
        self,
        auth_session: AuthSession,
        *,
        revoked_at: datetime,
    ) -> None:
        if auth_session.revoked_at is None:
            auth_session.revoked_at = revoked_at

        await self.session.flush()

    async def revoke_all_active_for_user(
        self,
        user_id: UUID,
        *,
        revoked_at: datetime,
    ) -> list[UUID]:
        statement = (
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > revoked_at,
            )
            .with_for_update()
        )

        result = await self.session.scalars(statement)
        sessions = list(result.all())

        for auth_session in sessions:
            auth_session.revoked_at = revoked_at

        await self.session.flush()

        return [auth_session.id for auth_session in sessions]

    async def revoke_replacement_chain(
        self,
        *,
        starting_session_id: UUID,
        revoked_at: datetime,
    ) -> list[UUID]:
        revoked_ids: list[UUID] = []
        visited_ids: set[UUID] = set()
        current_id: UUID | None = starting_session_id

        while current_id is not None:
            if current_id in visited_ids:
                raise RuntimeError("Cycle detected in auth-session replacement chain")

            visited_ids.add(current_id)

            statement = select(AuthSession).where(AuthSession.id == current_id).with_for_update()

            result = await self.session.execute(statement)
            current = result.scalar_one_or_none()

            if current is None:
                break

            if current.revoked_at is None:
                current.revoked_at = revoked_at

            revoked_ids.append(current.id)
            current_id = current.replaced_by_session_id

        await self.session.flush()

        return revoked_ids
