from __future__ import annotations

from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from pydantic.alias_generators import to_camel


class UserApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class UserCreateRequest(UserApiModel):
    email: str = Field(
        min_length=3,
        max_length=320,
    )
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    password: SecretStr = Field(
        min_length=12,
        max_length=128,
    )
    first_name: str = Field(
        min_length=1,
        max_length=100,
    )
    last_name: str = Field(
        min_length=1,
        max_length=100,
    )
    phone: str | None = Field(
        default=None,
        max_length=32,
    )
    role_ids: list[UUID] = Field(
        min_length=1,
        max_length=10,
    )

    @field_validator("email")
    @classmethod
    def validate_email(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().casefold()

        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("A valid email address is required")

        return normalized

    @field_validator(
        "username",
        "first_name",
        "last_name",
    )
    @classmethod
    def strip_text(
        cls,
        value: str,
    ) -> str:
        return value.strip()

    @field_validator("role_ids")
    @classmethod
    def reject_duplicate_roles(
        cls,
        value: list[UUID],
    ) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate role IDs are not allowed")

        return value


class UserStatusUpdateRequest(UserApiModel):
    is_active: bool


class UserResponse(UserApiModel):
    id: UUID
    email: str
    username: str
    first_name: str
    last_name: str
    phone: str | None
    is_active: bool
    mfa_enabled: bool


class UserListResponse(UserApiModel):
    items: list[UserResponse]
    total: int
    offset: int
    limit: int
