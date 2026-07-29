from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Secure Surveillance Platform API"
    app_env: Literal[
        "development",
        "test",
        "staging",
        "production",
    ] = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"  # noqa: S104 - required for container networking
    app_port: int = Field(default=8000, ge=1, le=65535)
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # Database
    database_url: str
    test_database_url: str | None = None
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_pool_timeout: int = Field(default=30, ge=1, le=300)
    database_echo: bool = False

    # Redis
    redis_url: str
    redis_socket_timeout: float = Field(default=3.0, gt=0, le=60)

    # JWT
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "secure-surveillance-api"
    jwt_audience: str = "secure-surveillance-clients"
    jwt_access_token_minutes: int = Field(default=15, ge=1, le=1440)
    jwt_refresh_token_days: int = Field(default=7, ge=1, le=90)
    jwt_leeway_seconds: int = Field(default=5, ge=0, le=60)

    # Authentication security
    refresh_token_bytes: int = Field(default=64, ge=32, le=128)
    auth_max_failed_attempts: int = Field(default=5, ge=3, le=20)
    auth_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    auth_mfa_challenge_minutes: int = Field(
        default=5,
        ge=1,
        le=30,
    )

    # HTTP security
    cors_origins: list[str] = Field(default_factory=list)
    trusted_hosts: list[str] = Field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
        ]
    )

    # Object storage
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: SecretStr = SecretStr("minioadmin")
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "evidence"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def validate_database_urls(cls, value: str | None) -> str | None:
        if value is None:
            return value

        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("Database URLs must use the postgresql+asyncpg driver")

        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()

        if len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")

        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
