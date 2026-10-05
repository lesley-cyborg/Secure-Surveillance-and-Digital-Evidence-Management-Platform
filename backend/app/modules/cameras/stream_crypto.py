from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.camera_stream_encryption_key
    if key is None:
        raise RuntimeError("CAMERA_STREAM_ENCRYPTION_KEY is not configured")
    return Fernet(key.get_secret_value().encode("utf-8"))


def encrypt_stream_url(plain_url: str) -> str:
    token = _fernet().encrypt(plain_url.strip().encode("utf-8"))
    return token.decode("utf-8")


def decrypt_stream_url(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid stream URL ciphertext") from exc