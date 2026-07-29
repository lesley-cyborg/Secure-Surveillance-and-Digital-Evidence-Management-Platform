from __future__ import annotations

from ipaddress import ip_address
from typing import NoReturn
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from app.modules.rbac.access_types import (
    AdministratorAccess,
)
from app.modules.users.dependencies import (
    UserManagementServiceDependency,
)
from app.modules.users.exceptions import (
    DuplicateUserError,
    LastAdministratorError,
    RoleAlreadyAssignedError,
    RoleAssignmentNotFoundError,
    RoleNotFoundError,
    SelfModificationForbiddenError,
    UserNotFoundError,
)
from app.modules.users.schemas import (
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserStatusUpdateRequest,
)
from app.modules.users.service import (
    UserManagementContext,
)

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


def _correlation_id(
    request: Request,
) -> str:
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


def _source_ip(
    request: Request,
) -> str | None:
    if request.client is None:
        return None

    host = request.client.host.split(
        "%",
        maxsplit=1,
    )[0]

    try:
        return str(ip_address(host))
    except ValueError:
        return None


def _context(
    request: Request,
    administrator: AdministratorAccess,
) -> UserManagementContext:
    user_agent = request.headers.get("User-Agent")

    if user_agent is not None:
        user_agent = user_agent[:4096]

    return UserManagementContext(
        actor_user_id=administrator.user.id,
        correlation_id=_correlation_id(request),
        source_ip=_source_ip(request),
        user_agent=user_agent,
    )


def _raise_user_management_error(
    exc: Exception,
) -> NoReturn:
    if isinstance(exc, UserNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = "USER_NOT_FOUND"
        message = "The requested user was not found."

    elif isinstance(exc, RoleNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = "ROLE_NOT_FOUND"
        message = "The requested role was not found."

    elif isinstance(exc, DuplicateUserError):
        status_code = status.HTTP_409_CONFLICT
        code = "USER_ALREADY_EXISTS"
        message = "A user with that email address or username already exists."

    elif isinstance(
        exc,
        RoleAlreadyAssignedError,
    ):
        status_code = status.HTTP_409_CONFLICT
        code = "ROLE_ALREADY_ASSIGNED"
        message = "The user already has that role."

    elif isinstance(
        exc,
        RoleAssignmentNotFoundError,
    ):
        status_code = status.HTTP_404_NOT_FOUND
        code = "ROLE_ASSIGNMENT_NOT_FOUND"
        message = "The user does not have that role."

    elif isinstance(
        exc,
        (
            SelfModificationForbiddenError,
            LastAdministratorError,
        ),
    ):
        status_code = status.HTTP_409_CONFLICT
        code = "UNSAFE_ADMINISTRATIVE_CHANGE"
        message = "The requested administrative change is not permitted."

    else:
        raise exc

    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    ) from exc


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    summary="Create a user",
    operation_id="createUser",
)
async def create_user(
    payload: UserCreateRequest,
    request: Request,
    administrator: AdministratorAccess,
    service: UserManagementServiceDependency,
) -> UserResponse:
    context = _context(
        request,
        administrator,
    )

    try:
        user = await service.create_user(
            payload=payload,
            context=context,
        )
    except (
        DuplicateUserError,
        RoleNotFoundError,
    ) as exc:
        _raise_user_management_error(exc)

    return UserResponse.model_validate(user)


@router.get(
    "",
    response_model=UserListResponse,
    summary="List users",
    operation_id="listUsers",
)
async def list_users(
    administrator: AdministratorAccess,
    service: UserManagementServiceDependency,
    offset: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
) -> UserListResponse:
    del administrator

    users, total = await service.list_users(
        offset=offset,
        limit=limit,
    )

    return UserListResponse(
        items=[UserResponse.model_validate(user) for user in users],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user",
    operation_id="getUser",
)
async def get_user(
    user_id: UUID,
    administrator: AdministratorAccess,
    service: UserManagementServiceDependency,
) -> UserResponse:
    del administrator

    try:
        user = await service.get_user(user_id)
    except UserNotFoundError as exc:
        _raise_user_management_error(exc)

    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    summary="Change user status",
    operation_id="updateUserStatus",
)
async def update_user_status(
    user_id: UUID,
    payload: UserStatusUpdateRequest,
    request: Request,
    administrator: AdministratorAccess,
    service: UserManagementServiceDependency,
) -> UserResponse:
    context = _context(
        request,
        administrator,
    )

    try:
        user = await service.set_active_status(
            user_id=user_id,
            is_active=payload.is_active,
            context=context,
        )
    except (
        UserNotFoundError,
        SelfModificationForbiddenError,
        LastAdministratorError,
    ) as exc:
        _raise_user_management_error(exc)

    return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Assign a role",
    operation_id="assignUserRole",
)
async def assign_user_role(
    user_id: UUID,
    role_id: UUID,
    request: Request,
    administrator: AdministratorAccess,
    service: UserManagementServiceDependency,
) -> Response:
    context = _context(
        request,
        administrator,
    )

    try:
        await service.assign_role(
            user_id=user_id,
            role_id=role_id,
            context=context,
        )
    except (
        UserNotFoundError,
        RoleNotFoundError,
        RoleAlreadyAssignedError,
    ) as exc:
        _raise_user_management_error(exc)

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "X-Correlation-ID": (context.correlation_id),
        },
    )


@router.delete(
    "/{user_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Remove a role",
    operation_id="removeUserRole",
)
async def remove_user_role(
    user_id: UUID,
    role_id: UUID,
    request: Request,
    administrator: AdministratorAccess,
    service: UserManagementServiceDependency,
) -> Response:
    context = _context(
        request,
        administrator,
    )

    try:
        await service.remove_role(
            user_id=user_id,
            role_id=role_id,
            context=context,
        )
    except (
        UserNotFoundError,
        RoleNotFoundError,
        RoleAssignmentNotFoundError,
        SelfModificationForbiddenError,
        LastAdministratorError,
    ) as exc:
        _raise_user_management_error(exc)

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "X-Correlation-ID": (context.correlation_id),
        },
    )
