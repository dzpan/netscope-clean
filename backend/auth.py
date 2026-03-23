"""Authentication utilities — password hashing, API key generation, and FastAPI dependency.

Password hashing uses PBKDF2-HMAC-SHA256 (stdlib hashlib).
API keys are prefixed ``ns_`` tokens validated by SHA-256 hash lookup.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status

if TYPE_CHECKING:
    from backend.auth_store import AuthStoreProtocol
    from backend.models import UserRole

_ITERATIONS = 260_000

# Module-level store reference — set by main.py at startup via set_auth_store()
_auth_store_ref: AuthStoreProtocol | None = None


def set_auth_store(store: AuthStoreProtocol) -> None:
    """Called by main.py at startup to inject the auth store (avoids circular import)."""
    global _auth_store_ref
    _auth_store_ref = store


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Return ``salt:hash`` using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    """Verify *password* against a ``salt:hash`` string."""
    try:
        salt_hex, hash_hex = stored.split(":", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return hmac.compare_digest(dk.hex(), hash_hex)


# ---------------------------------------------------------------------------
# API key generation
# ---------------------------------------------------------------------------


def generate_api_key() -> str:
    """Generate a ``ns_``-prefixed API key."""
    return "ns_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """Deterministic SHA-256 hash of an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Auth context
# ---------------------------------------------------------------------------


class AuthContext:
    """Resolved identity from a validated token."""

    __slots__ = ("user_id", "username", "role", "via_api_key")

    def __init__(
        self,
        user_id: str,
        username: str,
        role: UserRole,
        *,
        via_api_key: bool = False,
    ) -> None:
        self.user_id = user_id
        self.username = username
        self.role = role
        self.via_api_key = via_api_key


# ---------------------------------------------------------------------------
# FastAPI dependency — reads pre-validated AuthContext from request.state
# ---------------------------------------------------------------------------


async def require_auth(request: Request) -> AuthContext:
    """FastAPI dependency — reads the AuthContext set by AuthMiddleware.

    When auth is disabled, returns a synthetic admin context.
    When auth is enabled, the middleware already validated the token
    and stored the context in request.state.auth_context.
    """
    from backend.config import settings

    if not settings.auth_enabled:
        from backend.models import UserRole

        return AuthContext(user_id="anonymous", username="anonymous", role=UserRole.ADMIN)

    ctx: AuthContext | None = getattr(request.state, "auth_context", None)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx
