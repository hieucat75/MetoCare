"""Observability middleware: request id + access log + metrics (no PHI)."""

from __future__ import annotations

import logging
import uuid
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .context import request_id_var, user_id_var
from .metrics import registry

_access_logger = logging.getLogger("mcp.access")
REQUEST_ID_HEADER = "X-Request-ID"


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
