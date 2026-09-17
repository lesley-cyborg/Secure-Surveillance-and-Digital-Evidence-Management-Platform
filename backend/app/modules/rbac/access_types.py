from __future__ import annotations

from typing import Annotated, TypeAlias

from app.modules.rbac.dependencies import (
    AuthorizationContext,
    require_permission,
    require_role,
)
from fastapi import Depends

AdministratorAccess: TypeAlias = Annotated[
    AuthorizationContext,
    Depends(require_role("ADMINISTRATOR")),
]


EvidenceReader: TypeAlias = Annotated[
    AuthorizationContext,
    Depends(require_permission("evidence.read")),
]
