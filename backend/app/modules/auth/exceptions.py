from __future__ import annotations


class AuthenticationError(Exception):
    """Base exception for authentication-domain failures."""


class AuthenticationRejectedError(AuthenticationError):
    """
    Raised when authentication is rejected.

    The internal reason is preserved for auditing, but callers should
    return a generic message to avoid account enumeration.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("Authentication failed")


class RefreshTokenRejectedError(AuthenticationError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("Refresh token rejected")


class RefreshTokenReuseDetectedError(RefreshTokenRejectedError):
    """Raised when an already-rotated token is presented again."""


class AccessTokenRejectedError(AuthenticationError):
    """Raised when an access token or its session is invalid."""


class MfaVerificationRejectedError(AuthenticationRejectedError):
    """Raised when an MFA challenge cannot be trusted."""
