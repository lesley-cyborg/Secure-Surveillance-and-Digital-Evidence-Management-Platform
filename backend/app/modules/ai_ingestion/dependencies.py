from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.modules.ai_ingestion.security import (
    AIServiceAuthenticationError,
    AIServiceConfigurationError,
    AIServicePrincipal,
    AIServiceUnavailableError,
    authenticate_ai_service,
)
from app.modules.ai_ingestion.service import (
    DetectionEventIngestionService,
)

SettingsDependency = Annotated[
    Settings,
    Depends(get_settings),
]

AuthorizationHeader = Annotated[
    str | None,
    Header(alias="Authorization"),
]


async def require_ai_service(
    settings: SettingsDependency,
    authorization: AuthorizationHeader = None,
) -> AIServicePrincipal:
    try:
        return authenticate_ai_service(
            authorization_header=authorization,
            settings=settings,
        )

    except (
        AIServiceUnavailableError,
        AIServiceConfigurationError,
    ) as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI ingestion is unavailable",
        ) from exception

    except AIServiceAuthenticationError as exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service credentials",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from exception


AIServiceAccess = Annotated[
    AIServicePrincipal,
    Depends(require_ai_service),
]

DatabaseSession = Annotated[
    AsyncSession,
    Depends(get_db_session),
]


def get_detection_event_ingestion_service(
    session: DatabaseSession,
) -> DetectionEventIngestionService:
    return DetectionEventIngestionService(
        session=session,
    )


DetectionEventIngestionServiceAccess = Annotated[
    DetectionEventIngestionService,
    Depends(get_detection_event_ingestion_service),
]
