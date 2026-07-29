from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from getpass import getpass
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models.enums import AuditOutcome
from app.modules.audit.actions import AuditAction
from app.modules.audit.repository import AuditRepository
from app.modules.auth.repository import (
    UserRepository,
)
from app.modules.rbac.repository import (
    RBACRepository,
)

ADMINISTRATOR_ROLE_NAME = "ADMINISTRATOR"


class AdminBootstrapError(Exception):
    """Raised when admin bootstrap cannot proceed."""


async def bootstrap_admin(
    session: AsyncSession,
    *,
    email: str,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
) -> str:
    now = datetime.now(UTC).replace(microsecond=0)

    users = UserRepository(session)
    rbac = RBACRepository(session)
    audit = AuditRepository(session)

    try:
        administrator_role = await rbac.get_role_by_name(ADMINISTRATOR_ROLE_NAME)

        if administrator_role is None:
            raise AdminBootstrapError(
                "The ADMINISTRATOR role is missing. Run RBAC seed migrations first."
            )

        existing_admin_count = await rbac.count_active_users_with_role(
            role_id=administrator_role.id,
            now=now,
        )

        if existing_admin_count > 0:
            raise AdminBootstrapError(
                "An active administrator already exists. Bootstrap was refused."
            )

        existing_email = await users.get_by_email(
            email,
            include_deleted=True,
        )

        if existing_email is not None:
            raise AdminBootstrapError("The supplied email address already exists.")

        existing_username = await users.get_by_username(
            username,
            include_deleted=True,
        )

        if existing_username is not None:
            raise AdminBootstrapError("The supplied username already exists.")

        user = await users.create(
            email=email,
            username=username,
            password_hash=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )

        await rbac.assign_role(
            user_id=user.id,
            role_id=administrator_role.id,
            assigned_by=None,
            assigned_at=now,
        )

        correlation_id = str(uuid4())

        await audit.create(
            actor_user_id=None,
            action=AuditAction.USER_CREATED,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.SUCCESS,
            correlation_id=correlation_id,
            occurred_at=now,
            details={
                "bootstrap": True,
                "username": user.username,
            },
        )

        await audit.create(
            actor_user_id=None,
            action=AuditAction.ADMIN_BOOTSTRAPPED,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.SUCCESS,
            correlation_id=correlation_id,
            occurred_at=now,
            details={
                "role_id": str(administrator_role.id),
                "role_name": (administrator_role.name),
            },
        )

        await session.commit()

        return str(user.id)

    except Exception:
        await session.rollback()
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Create the platform's first administrator account.")
    )

    parser.add_argument(
        "--email",
        required=True,
    )
    parser.add_argument(
        "--username",
        required=True,
    )
    parser.add_argument(
        "--first-name",
        required=True,
    )
    parser.add_argument(
        "--last-name",
        required=True,
    )

    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()

    password = getpass("Administrator password: ")
    confirmation = getpass("Confirm administrator password: ")

    if password != confirmation:
        raise AdminBootstrapError("Passwords do not match.")

    if len(password) < 12:
        raise AdminBootstrapError("Password must contain at least 12 characters.")

    settings = get_settings()

    engine = create_async_engine(
        str(settings.database_url),
        pool_pre_ping=True,
    )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with session_factory() as session:
            user_id = await bootstrap_admin(
                session,
                email=args.email,
                username=args.username,
                password=password,
                first_name=args.first_name,
                last_name=args.last_name,
            )

        print(f"Administrator created successfully. User ID: {user_id}")

    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
