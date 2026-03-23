"""Authentication router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from backend.auth import (
    AuthContext,
    generate_api_key,
    hash_api_key,
    hash_password,
    require_auth,
    verify_password,
)
from backend.models import (
    APIKey as APIKeyModel,
)
from backend.models import (
    CreateAPIKeyRequest,
    CreateUserRequest,
    LoginRequest,
    TokenResponse,
    UserRole,
)
from backend.models import (
    User as UserModel,
)
from backend.rate_limit import limiter

router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("5/minute")
async def login(request: Request, req: LoginRequest) -> TokenResponse:
    """Authenticate with username/password and receive an API key."""
    _auth_store = request.app.state.auth_store
    user = _auth_store.get_user_by_username(req.username)
    if user is None or user.disabled or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    from datetime import timedelta

    raw_key = generate_api_key()
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    api_key = APIKeyModel(
        id=str(uuid4()),
        key_hash=hash_api_key(raw_key),
        label=f"login-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
        user_id=user.id,
        role=user.role,
        created_at=datetime.now(UTC),
        expires_at=expires_at,
    )
    await _auth_store.create_api_key(api_key)
    return TokenResponse(
        token=raw_key,
        user_id=user.id,
        username=user.username,
        role=user.role,
        expires_at=api_key.expires_at,
    )


@router.get("/auth/me", tags=["Auth"])
async def auth_me(ctx: AuthContext = Depends(require_auth)) -> dict[str, str]:
    """Return the authenticated user's identity."""
    return {"user_id": ctx.user_id, "username": ctx.username, "role": ctx.role}


@router.post("/auth/users", status_code=201, tags=["Auth"])
async def create_user(
    request: Request, req: CreateUserRequest, ctx: AuthContext = Depends(require_auth)
) -> dict[str, str]:
    """Create a new user (admin only)."""
    _auth_store = request.app.state.auth_store
    if ctx.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    if _auth_store.get_user_by_username(req.username) is not None:
        raise HTTPException(status_code=409, detail="Username already exists")

    user = UserModel(
        id=str(uuid4()),
        username=req.username,
        password_hash=hash_password(req.password),
        role=req.role,
        created_at=datetime.now(UTC),
    )
    await _auth_store.create_user(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/auth/users", tags=["Auth"])
async def list_users(
    request: Request, ctx: AuthContext = Depends(require_auth)
) -> list[dict[str, str]]:
    """List all users (admin only). Password hashes are never returned."""
    _auth_store = request.app.state.auth_store
    if ctx.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return [
        {"id": u.id, "username": u.username, "role": u.role, "disabled": str(u.disabled)}
        for u in _auth_store.list_users()
    ]


@router.post("/auth/api-keys", status_code=201, tags=["Auth"])
async def create_api_key_endpoint(
    request: Request, req: CreateAPIKeyRequest, ctx: AuthContext = Depends(require_auth)
) -> dict[str, str]:
    """Create a new API key for the authenticated user. Returns the raw key once."""
    _auth_store = request.app.state.auth_store
    from datetime import timedelta

    raw_key = generate_api_key()
    expires_at = None
    if req.expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=req.expires_in_days)

    api_key = APIKeyModel(
        id=str(uuid4()),
        key_hash=hash_api_key(raw_key),
        label=req.label,
        user_id=ctx.user_id,
        role=UserRole(ctx.role),
        created_at=datetime.now(UTC),
        expires_at=expires_at,
    )
    await _auth_store.create_api_key(api_key)
    return {"id": api_key.id, "key": raw_key, "label": req.label}


@router.get("/auth/api-keys", tags=["Auth"])
async def list_api_keys(
    request: Request,
    ctx: AuthContext = Depends(require_auth),
) -> list[dict[str, str | None]]:
    """List API keys for the authenticated user. Hashes are never returned."""
    _auth_store = request.app.state.auth_store
    return [
        {
            "id": k.id,
            "label": k.label,
            "role": k.role,
            "created_at": k.created_at.isoformat(),
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "disabled": str(k.disabled),
        }
        for k in _auth_store.list_api_keys(ctx.user_id)
    ]


@router.delete("/auth/api-keys/{key_id}", status_code=204, tags=["Auth"])
async def delete_api_key_endpoint(
    request: Request, key_id: str, ctx: AuthContext = Depends(require_auth)
) -> Response:
    """Delete an API key. Users can delete their own keys; admins can delete any."""
    _auth_store = request.app.state.auth_store
    key = _auth_store.get_api_key(key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if key.user_id != ctx.user_id and ctx.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Cannot delete another user's key")
    await _auth_store.delete_api_key(key_id)
    return Response(status_code=204)
