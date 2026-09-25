from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import Settings


def test_production_model_requires_checksum() -> None:
    with pytest.raises(
        ValidationError,
        match="AI_MODEL_SHA256 is required",
    ):
        Settings(
            _env_file=None,
            production_model_enabled=True,
            model_sha256=None,
        )


def test_development_configuration_can_omit_checksum() -> None:
    settings = Settings(
        _env_file=None,
        production_model_enabled=False,
        model_sha256=None,
    )

    assert settings.model_sha256 is None


def test_production_model_accepts_valid_checksum() -> None:
    checksum = "a" * 64
    settings = Settings(
        _env_file=None,
        production_model_enabled=True,
        model_sha256=checksum,
    )

    assert settings.model_sha256 == checksum


def test_enabled_addon_model_requires_global_enable_and_checksum() -> None:
    with pytest.raises(
        ValidationError,
        match="AI_ADDON_ENABLED must be true",
    ):
        Settings(
            _env_file=None,
            addon_threat_model_enabled=True,
            addon_threat_model_sha256="a" * 64,
        )

    with pytest.raises(
        ValidationError,
        match="SHA-256 digests are required",
    ):
        Settings(
            _env_file=None,
            addon_enabled=True,
            addon_threat_model_enabled=True,
        )


def test_addon_event_v11_requires_addon_enablement() -> None:
    with pytest.raises(
        ValidationError,
        match="AI_ADDON_ENABLED must be true",
    ):
        Settings(
            _env_file=None,
            addon_event_v11_enabled=True,
        )
