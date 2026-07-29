from __future__ import annotations

from typing import Annotated, TypeAlias

from fastapi import Depends

from app.modules.auth.dependencies import (
    DatabaseSession,
    RevocationStoreDependency,
)
from app.modules.users.service import (
    UserManagementService,
)


def get_user_management_service(
    session: DatabaseSession,
    revocations: RevocationStoreDependency,
) -> UserManagementService:
    return UserManagementService(
        session=session,
        revocations=revocations,
    )


UserManagementServiceDependency: TypeAlias = Annotated[
    UserManagementService,
    Depends(get_user_management_service),
]
