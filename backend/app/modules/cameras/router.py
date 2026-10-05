from __future__ import annotations
from datetime import UTC, datetime
from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.surveillance import Camera, Site
from app.db.models.enums import CameraStatus
from app.db.session import get_db_session

from app.core.config import get_settings

from app.modules.cameras.connectivity import probe_camera_endpoint
from app.modules.cameras.stream_crypto import(
encrypt_stream_url,
decrypt_stream_url,
) 
from app.modules.cameras.schemas import (
    CameraCreateRequest,
    CameraListResponse,
    CameraResponse,
    CameraTestResponse,
    CameraHeartbeatRequest,
    CameraHeartbeatResponse,
)
from app.modules.rbac.dependencies import (
    AuthorizationContext,
    require_permission,
)

router = APIRouter(prefix="/cameras", tags=["Cameras"])

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def _to_response(camera: Camera) -> CameraResponse:
    return CameraResponse(
        id=camera.id,
        site_id=camera.site_id,
        name=camera.name,
        camera_code=camera.camera_code,
        ip_address=str(camera.ip_address),  # IPv4Address → str
        protocol=camera.protocol,
        status=camera.status,
        location_description=camera.location_description,
        is_active=camera.is_active,
        last_seen_at=camera.last_seen_at,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


@router.get(
    "",
    response_model=CameraListResponse,
    response_model_by_alias=True,
    summary="List cameras",
)
async def list_cameras(
    session: DbSession,
    _: Annotated[
        AuthorizationContext,
        Depends(require_permission("cameras.read")),
    ],
) -> CameraListResponse:
    result = await session.execute(
        select(Camera).order_by(Camera.camera_code.asc())
    )
    cameras = list(result.scalars().all())
    return CameraListResponse(
        items=[_to_response(c) for c in cameras],
        total=len(cameras),
    )


@router.get(
    "/{camera_id}",
    response_model=CameraResponse,
    response_model_by_alias=True,
    summary="Get a camera",
)
async def get_camera(
    camera_id: str,
    session: DbSession,
    _: Annotated[
        AuthorizationContext,
        Depends(require_permission("cameras.read")),
    ],
) -> CameraResponse:
    from uuid import UUID

    try:
        cid = UUID(camera_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_ID", "message": "camera_id must be a UUID"},
        ) from exc

    camera = await session.scalar(select(Camera).where(Camera.id == cid))
    if camera is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CAMERA_NOT_FOUND", "message": "Camera not found"},
        )
    return _to_response(camera)


@router.post(
    "",
    response_model=CameraResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Register a camera",
)
async def create_camera(
    body: CameraCreateRequest,
    session: DbSession,
    auth: Annotated[
        AuthorizationContext,
        Depends(require_permission("cameras.create")),
    ],
) -> CameraResponse:
    site = await session.scalar(select(Site).where(Site.id == body.site_id))
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SITE_NOT_FOUND",
                "message": "The specified site does not exist.",
            },
        )

    try:
        encrypted_url = encrypt_stream_url(body.stream_url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "STREAM_ENCRYPTION_FAILED",
                "message": "Could not encrypt stream URL. Check CAMERA_STREAM_ENCRYPTION_KEY.",
            },
        ) from exc

    camera = Camera(
        site_id=body.site_id,
        registered_by=auth.user.id,
        name=body.name,
        camera_code=body.camera_code,
        ip_address=body.ip_address,
        protocol=body.protocol,  # already RTSP/ONVIF/HTTPS from schema
        stream_url_encrypted=encrypted_url,
        credentials_secret_ref=body.credentials_secret_ref,
        status=body.status,
        location_description=body.location_description,
        is_active=body.is_active,
        last_seen_at=None,
    )
   
    session.add(camera)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raw = str(exc.orig) if getattr(exc, "orig", None) is not None else str(exc)
        code = "CAMERA_CODE_CONFLICT" if "camera_code" in raw.lower() else "INTEGRITY_ERROR"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "message": raw},
        ) from None

    await session.refresh(camera)
    return _to_response(camera)


@router.post(
    "/{camera_id}/test",
    response_model=CameraTestResponse,
    response_model_by_alias=True,
    summary="Test camera connectivity",
)
async def test_camera(
    camera_id: str,
    session: DbSession,
    _: Annotated[
        AuthorizationContext,
        Depends(require_permission("cameras.test")),
    ],
) -> CameraTestResponse:
    try:
        cid = UUID(camera_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_ID", "message": "camera_id must be a UUID"},
        ) from exc

    camera = await session.scalar(select(Camera).where(Camera.id == cid))
    if camera is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CAMERA_NOT_FOUND", "message": "Camera not found"},
        )

    try:
        plain_url = decrypt_stream_url(camera.stream_url_encrypted)
    except ValueError:
        # Seed placeholders cannot decrypt — fall back to IP:554 probe only
        plain_url = f"rtsp://{camera.ip_address}:554/"

    reachable, latency_ms, message = await probe_camera_endpoint(
        ip_address=str(camera.ip_address),
        protocol=camera.protocol,
        stream_url=plain_url,
    )

    # Optional: update status from probe
    camera.status = CameraStatus.ONLINE if reachable else CameraStatus.OFFLINE
    camera.last_seen_at = datetime.now(UTC) if reachable else camera.last_seen_at
    await session.commit()

    return CameraTestResponse(
        camera_id=camera.id,
        reachable=reachable,
        latency_ms=latency_ms,
        message=message,
        checked_status=camera.status,
    )

def _require_ai_service_token(authorization: str | None) -> None:
    settings = get_settings()
    expected = settings.ai_ingestion_service_token
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service token not configured",
        )
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )
    value = authorization.strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    if value != expected.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )


@router.patch(
    "/{camera_id}/heartbeat",
    response_model=CameraHeartbeatResponse,
    response_model_by_alias=True,
    summary="Camera heartbeat from AI worker",
    include_in_schema=True,  # or False for internal-only
)
async def camera_heartbeat(
    camera_id: str,
    body: CameraHeartbeatRequest,
    session: DbSession,
    authorization: str | None = Header(default = None, alias="Authorization"),
) -> CameraHeartbeatResponse:
    _require_ai_service_token(authorization)

    try:
        cid = UUID(camera_id)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_ID", "message": "..."}) from exc

    camera = await session.scalar(select(Camera).where(Camera.id == cid))
    if camera is None:
        raise HTTPException(404, detail={"code": "CAMERA_NOT_FOUND", "message": "..."})

    camera.status = body.status
    camera.last_seen_at = body.last_seen_at or datetime.now(UTC)
    await session.commit()
    await session.refresh(camera)

    return CameraHeartbeatResponse(
        camera_id=camera.id,
        status=camera.status,
        last_seen_at=camera.last_seen_at,
    )








