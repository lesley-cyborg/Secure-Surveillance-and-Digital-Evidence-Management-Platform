from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from pydantic.alias_generators import to_camel


class MfaVerifyRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    challenge_id: UUID = Field(alias="challengeId")

    code: SecretStr = Field(
        min_length=6,
        max_length=12,
    )


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class LoginRequest(APIModel):
    identifier: str = Field(
        min_length=3,
        max_length=320,
        description="Email address or username",
    )
    password: SecretStr = Field(
        min_length=8,
        max_length=1024,
    )

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("Identifier must not be empty")

        return normalized


class AuthenticatedUser(APIModel):
    id: UUID
    email: str
    username: str
    first_name: str
    last_name: str
    mfa_enabled: bool
    roles: list[str]
    permissions: list[str]


class TokenPair(APIModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type, not a credential
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class AuthResponse(APIModel):
    user: AuthenticatedUser
    tokens: TokenPair


class MfaChallengeResponse(APIModel):
    mfa_required: Literal[True] = True
    challenge_id: UUID
    expires_at: datetime
    message: str = "MFA verification is required"


class AuthErrorDetail(APIModel):
    code: str
    message: str


class AuthErrorResponse(APIModel):
    detail: AuthErrorDetail


class RefreshTokenRequest(APIModel):
    refresh_token: SecretStr = Field(
        min_length=20,
        max_length=1024,
    )


class LogoutRequest(APIModel):
    refresh_token: SecretStr | None = None

    # Keeps logout-all under the existing OpenAPI logout operation.
    all_sessions: bool = False
