from __future__ import annotations

from ipaddress import ip_address
from uuid import uuid4

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.modules.auth.dependencies import (
    AuthenticationServiceDependency,
    CurrentAccessTokenDependency,
)
from app.modules.auth.exceptions import (
    AuthenticationRejectedError,
    MfaVerificationRejectedError,
    RefreshTokenRejectedError,
    RefreshTokenReuseDetectedError,
)
from app.modules.auth.schemas import (
    AuthErrorResponse,
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    MfaChallengeResponse,
    MfaVerifyRequest,
    RefreshTokenRequest,
    TokenPair,
)
from app.modules.auth.service import (
    AccessSessionContext,
    LoginContext,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def _get_correlation_id(request: Request) -> str:
    value = getattr(
        request.state,
        "correlation_id",
        None,
    )

    if value is None:
        value = request.headers.get("X-Correlation-ID")

    if value is None:
        value = str(uuid4())

    return str(value)[:64]


def _get_source_ip(request: Request) -> str | None:
    if request.client is None:
        return None

    host = request.client.host

    # Remove an IPv6 zone identifier when present.
    normalized_host = host.split("%", maxsplit=1)[0]

    try:
        return str(ip_address(normalized_host))
    except ValueError:
        return None


def _get_login_context(
    request: Request,
) -> LoginContext:
    user_agent = request.headers.get("User-Agent")

    if user_agent is not None:
        user_agent = user_agent[:4096]

    return LoginContext(
        correlation_id=_get_correlation_id(request),
        source_ip=_get_source_ip(request),
        user_agent=user_agent,
    )


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=AuthResponse,
    response_model_exclude_none=True,
    responses={
        status.HTTP_202_ACCEPTED: {
            "model": MfaChallengeResponse,
            "description": ("Primary credentials are valid and MFA verification is required."),
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": AuthErrorResponse,
            "description": "Authentication failed.",
        },
    },
    summary="Authenticate a user",
    operation_id="loginUser",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthenticationServiceDependency,
) -> AuthResponse | JSONResponse:
    context = _get_login_context(request)

    try:
        result = await service.login(
            payload,
            context,
        )
    except AuthenticationRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": ("The supplied authentication credentials are invalid."),
            },
            headers={
                "WWW-Authenticate": "Bearer",
                "X-Correlation-ID": (context.correlation_id),
            },
        ) from exc

    if isinstance(result, MfaChallengeResponse):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=jsonable_encoder(
                result,
                by_alias=True,
            ),
            headers={
                "X-Correlation-ID": (context.correlation_id),
            },
        )

    response.headers["X-Correlation-ID"] = context.correlation_id

    return result


@router.post(
    "/mfa/verify",
    response_model=AuthResponse,
    response_model_exclude_none=True,
    summary="Verify an MFA challenge",
    operation_id="verifyMfaChallenge",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": AuthErrorResponse,
            "description": ("The challenge or code is invalid."),
        },
    },
)
async def verify_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    response: Response,
    service: AuthenticationServiceDependency,
) -> AuthResponse:
    context = _get_login_context(request)

    try:
        result = await service.verify_mfa(
            payload,
            context,
        )

    except MfaVerificationRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "MFA_VERIFICATION_FAILED",
                "message": ("The verification code is invalid or expired."),
            },
            headers={
                "X-Correlation-ID": (context.correlation_id),
            },
        ) from exc

    response.headers["X-Correlation-ID"] = context.correlation_id

    return result


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a refresh token",
    operation_id="refreshAccessToken",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": AuthErrorResponse,
        },
    },
)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    request: Request,
    response: Response,
    service: AuthenticationServiceDependency,
) -> TokenPair:
    context = _get_login_context(request)

    try:
        result = await service.refresh(
            payload,
            context,
        )

    except RefreshTokenReuseDetectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": ("REFRESH_TOKEN_REUSE_DETECTED"),
                "message": ("The session is no longer valid. Sign in again."),
            },
            headers={
                "X-Correlation-ID": (context.correlation_id),
            },
        ) from exc

    except RefreshTokenRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_REFRESH_TOKEN",
                "message": ("The refresh token is invalid or expired."),
            },
            headers={
                "X-Correlation-ID": (context.correlation_id),
            },
        ) from exc

    response.headers["X-Correlation-ID"] = context.correlation_id

    return result


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Log out the current user",
    operation_id="logoutUser",
)
async def logout(
    request: Request,
    service: AuthenticationServiceDependency,
    current: CurrentAccessTokenDependency,
    payload: LogoutRequest | None = None,
) -> Response:
    request_context = _get_login_context(request)

    access_context = AccessSessionContext(
        user_id=current.user.id,
        session_id=current.auth_session.id,
        access_token_jti=current.claims.jti,
        access_token_expires_at=(current.claims.exp),
        correlation_id=(request_context.correlation_id),
        source_ip=request_context.source_ip,
        user_agent=request_context.user_agent,
    )

    try:
        await service.logout(
            payload,
            access_context,
        )
    except RefreshTokenRejectedError as exc:
        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail={
                "code": "INVALID_REFRESH_TOKEN",
                "message": ("The supplied refresh token does not match this account."),
            },
        ) from exc

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "X-Correlation-ID": (request_context.correlation_id),
        },
    )
