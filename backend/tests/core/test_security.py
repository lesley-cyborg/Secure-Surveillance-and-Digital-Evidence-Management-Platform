from datetime import timedelta
from uuid import uuid4

import pytest
from app.core.security import (
    ExpiredAccessTokenError,
    InvalidAccessTokenError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    password_needs_rehash,
    refresh_token_matches,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    plaintext = "Local-Test-Credential-Only-123!"
    encoded = hash_password(plaintext)

    assert encoded != plaintext
    assert encoded.startswith("$argon2id$")
    assert verify_password(plaintext, encoded) is True


def test_wrong_password_is_rejected() -> None:
    encoded = hash_password("Local-Test-Credential-Only-123!")

    assert (
        verify_password(
            "Incorrect-Test-Credential-456!",
            encoded,
        )
        is False
    )


def test_invalid_password_hash_is_rejected() -> None:
    assert (
        verify_password(
            "Local-Test-Credential-Only-123!",
            "not-an-argon2-hash",
        )
        is False
    )

    assert password_needs_rehash("not-an-argon2-hash") is True


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    session_id = uuid4()

    issued = create_access_token(
        user_id=user_id,
        session_id=session_id,
    )

    claims = decode_access_token(issued.token)

    assert claims.sub == user_id
    assert claims.sid == session_id
    assert claims.jti == issued.jti
    assert claims.typ == "access"
    assert claims.exp == issued.expires_at


def test_expired_access_token_is_rejected() -> None:
    issued = create_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        expires_delta=timedelta(seconds=-30),
    )

    with pytest.raises(ExpiredAccessTokenError):
        decode_access_token(issued.token)


def test_tampered_access_token_is_rejected() -> None:
    issued = create_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
    )

    header, payload, signature = issued.token.split(".")
    tampered_payload = payload[:-1] + ("A" if payload[-1] != "A" else "B")
    tampered_token = ".".join([header, tampered_payload, signature])

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(tampered_token)


def test_refresh_token_is_hashed_and_verifiable() -> None:
    issued = create_refresh_token()

    assert issued.token != issued.token_hash
    assert len(issued.token_hash) == 64

    assert (
        refresh_token_matches(
            issued.token,
            issued.token_hash,
        )
        is True
    )

    assert (
        refresh_token_matches(
            "wrong-refresh-token",
            issued.token_hash,
        )
        is False
    )


def test_refresh_rotation_preserves_family() -> None:
    original = create_refresh_token()

    rotated = create_refresh_token(family_id=original.family_id)

    assert rotated.family_id == original.family_id
    assert rotated.jti != original.jti
    assert rotated.token != original.token
    assert rotated.token_hash != original.token_hash
