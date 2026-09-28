from __future__ import annotations
import hashlib
from pathlib import Path

class ModelIntegrityError(ValueError):
    pass

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

def validate_model_file(path: Path, expected_sha256: str | None = None) -> None:
    if not path.is_file():
        raise ModelIntegrityError(f"model file does not exist: {path}")
    if expected_sha256 is None:
        return
    expected = expected_sha256.strip().casefold()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ModelIntegrityError("expected_sha256 must be a 64-character hexadecimal digest")
    actual = sha256_file(path)
    if actual != expected:
        raise ModelIntegrityError(f"model checksum mismatch: {path}")
