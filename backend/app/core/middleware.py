from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.context import correlation_id_ctx


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Correlation-ID")
        try:
            correlation_id = str(UUID(incoming)) if incoming else str(uuid4())
        except ValueError:
            correlation_id = str(uuid4())

        token = correlation_id_ctx.set(correlation_id)
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)

        response.headers["X-Correlation-ID"] = correlation_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        return response
