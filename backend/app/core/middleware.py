"""Observability middleware: request id + access log + metrics (no PHI)."""

from __future__ import annotations

import logging
import uuid
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .context import request_id_var, user_id_var
from .metrics import registry
from .security import decode_token

_access_logger = logging.getLogger("mcp.access")
REQUEST_ID_HEADER = "X-Request-ID"

# Paths reachable while a doctor/admin still owes MFA enrollment.
_ENROLL_ALLOW_SUFFIXES = (
    "/auth/mfa/enroll",
    "/auth/mfa/verify",
    "/auth/me",
    "/auth/logout",
    "/auth/login",
    "/auth/register",
    "/auth/refresh",
)
_ENROLL_ALLOW_EXACT = frozenset({"/health", "/metrics", "/docs", "/openapi.json", "/redoc"})


class MfaEnrollmentMiddleware(BaseHTTPMiddleware):
    """Force doctors/admins to enroll MFA before using any protected resource.

    If the bearer token carries `mfa_enrollment_required`, all paths are blocked
    (403) except the allowlist needed to complete enrollment.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        authz = request.headers.get("Authorization", "")
        if authz.startswith("Bearer "):
            payload = decode_token(authz[7:])
            if payload and payload.get("mfa_enrollment_required"):
                from app.core.config import get_settings as _gs

                if _gs().skip_mfa_in_dev:
                    return await call_next(request)
                path = request.url.path
                if path not in _ENROLL_ALLOW_EXACT and not path.endswith(_ENROLL_ALLOW_SUFFIXES):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "code": "mfa_enrollment_required",
                            "message": "MFA enrollment is required before accessing this resource.",
                        },
                    )
        return await call_next(request)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        rid_token = request_id_var.set(request_id)
        uid_token = user_id_var.set("-")
        start = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = perf_counter() - start
            # Prefer the route template over the raw path to bound label cardinality.
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            # A downstream dependency may have recorded the authenticated user id.
            user_id = getattr(request.state, "user_id", None) or user_id_var.get()
            user_id_var.set(user_id or "-")  # ensure the access log line is correlated

            labels = {"method": request.method, "path": path, "status": str(status_code)}
            registry.inc_counter("http_requests_total", labels)
            registry.observe(
                "http_request_duration_seconds",
                duration,
                {"method": request.method, "path": path},
            )
            if status_code >= 500:
                registry.inc_counter(
                    "http_server_errors_total", {"method": request.method, "path": path}
                )

            _access_logger.info(
                "http_request",
                extra={
                    "event": "http_request",
                    "method": request.method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            try:
                response.headers[REQUEST_ID_HEADER] = request_id
            except (NameError, UnboundLocalError):  # call_next raised
                pass
            user_id_var.reset(uid_token)
            request_id_var.reset(rid_token)
