from __future__ import annotations


class UserManagementError(Exception):
    """Base error for user-management operations."""


class UserNotFoundError(UserManagementError):
    """Raised when a requested user does not exist."""


class DuplicateUserError(UserManagementError):
    """Raised when an email address or username already exists."""


class RoleNotFoundError(UserManagementError):
    """Raised when a requested role does not exist."""


class RoleAlreadyAssignedError(UserManagementError):
    """Raised when a user already has the requested role."""


class RoleAssignmentNotFoundError(UserManagementError):
    """Raised when the requested role assignment does not exist."""


class SelfModificationForbiddenError(UserManagementError):
    """Raised when an administrator attempts an unsafe self-modification."""


class LastAdministratorError(UserManagementError):
    """Raised when an operation would remove the final administrator."""
