from __future__ import annotations


class CustodyError(Exception):
    """Base custody domain error."""


class CustodyEvidenceNotFoundError(CustodyError):
    """Referenced evidence does not exist."""


class CustodyIdempotencyConflictError(CustodyError):
    """An idempotency key was reused with another request."""


class CustodyChainIntegrityError(CustodyError):
    """The custody chain link is invalid or corrupted."""
    

class CustodyActorNotFoundError(Exception):
    """Raised when the custody actor does not exist."""    
    
