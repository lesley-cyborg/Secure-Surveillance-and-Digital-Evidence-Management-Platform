from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.custody.service import CustodyService
from app.modules.evidence.dependencies import ForensicSignerAccess

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db_session),
]


def get_custody_service(
    session: DatabaseSession,
    signer: ForensicSignerAccess,
) -> CustodyService:
    return CustodyService(
        session=session,
        signer=signer,
    )


CustodyServiceAccess = Annotated[
    CustodyService,
    Depends(get_custody_service),
]
