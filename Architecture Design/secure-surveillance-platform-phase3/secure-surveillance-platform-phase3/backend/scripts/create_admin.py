from __future__ import annotations

import argparse
import asyncio
from getpass import getpass

from argon2 import PasswordHasher
from sqlalchemy import select

from app.db.models.identity import Role, User, UserRole
from app.db.session import AsyncSessionFactory


async def create_admin(email: str, username: str, first_name: str, last_name: str, password: str) -> None:
    password_hasher = PasswordHasher()
    async with AsyncSessionFactory() as session:
        existing = await session.scalar(
            select(User).where((User.email == email.lower()) | (User.username == username.lower()))
        )
        if existing is not None:
            raise RuntimeError("A user with that email or username already exists")

        role = await session.scalar(select(Role).where(Role.name == "ADMINISTRATOR"))
        if role is None:
            raise RuntimeError("ADMINISTRATOR role is missing; run `alembic upgrade head` first")

        user = User(
            email=email.lower(),
            username=username.lower(),
            password_hash=password_hasher.hash(password),
            first_name=first_name,
            last_name=last_name,
            mfa_enabled=False,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id, assigned_by=None))
        await session.commit()
        print(f"Created administrator {user.email} ({user.id})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the first platform administrator")
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    secret = getpass("Administrator password: ")
    if len(secret) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    asyncio.run(
        create_admin(
            email=args.email,
            username=args.username,
            first_name=args.first_name,
            last_name=args.last_name,
            password=secret,
        )
    )
