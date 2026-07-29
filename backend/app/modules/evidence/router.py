from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.rbac.dependencies import (
    AuthorizationContext,
    require_any_permission,
    require_permission,
)

from app.modules.rbac.access_types import (
    AdministratorAccess,
    EvidenceReader,
)

router = APIRouter(
    prefix="/evidence",
    tags=["Evidence"],
)


@router.get("/{evidence_id}")
async def get_evidence(
    evidence_id: UUID,
    _: Annotated[
        AuthorizationContext,
        Depends(
            require_permission("evidence:read")
        ),
    ],
) -> dict[str, str]:
    return {
        "evidenceId": str(evidence_id),
    }


@router.get("/{evidence_id}/content")
async def stream_evidence(
    evidence_id: UUID,
    _: Annotated[
        AuthorizationContext,
        Depends(
            require_any_permission(
                "evidence:read",
                "evidence:investigate",
                "evidence:admin",
            )
        ),
    ],
) -> dict[str, str]:
    return {
        "evidenceId": str(evidence_id),
    }