"""Rate limiting configuration using slowapi."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import settings

# Default: 60 requests/minute per client IP for all endpoints.
# Sensitive endpoints override this with tighter limits via @limiter.limit().
_default_limits: list[str] = ["60/minute"] if settings.rate_limit_enabled else []

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=_default_limits,  # type: ignore[arg-type]
    enabled=settings.rate_limit_enabled,
)
