"""Request-scoped context variables for log correlation (no PHI)."""

from __future__ import annotations

import contextvars

# Correlation id for a single request; propagated via the X-Request-ID header.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
# Authenticated user id (opaque UUID — NOT PHI). "-" when anonymous.
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="-")
