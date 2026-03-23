"""Integration tests for authentication API endpoints."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.auth import generate_api_key, hash_api_key, hash_password
from backend.main import _auth_store, app
from backend.models import APIKey, User, UserRole


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.fixture
async def admin_user():
    """Create a test admin user and API key, return the raw key."""
    user = User(
        id=str(uuid4()),
        username=f"testadmin-{uuid4().hex[:8]}",
        password_hash=hash_password("admin-password-123"),
        role=UserRole.ADMIN,
        created_at=datetime.now(UTC),
    )
    await _auth_store.create_user(user)

    raw_key = generate_api_key()
    api_key = APIKey(
        id=str(uuid4()),
        key_hash=hash_api_key(raw_key),
        label="test-admin-key",
        user_id=user.id,
        role=UserRole.ADMIN,
        created_at=datetime.now(UTC),
    )
    await _auth_store.create_api_key(api_key)
    return {"user": user, "raw_key": raw_key, "api_key": api_key}


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    """Health endpoint should always be accessible."""
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_me_without_token(client):
    """When auth is disabled (default), /auth/me returns anonymous."""
    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "anonymous"


@pytest.mark.asyncio
async def test_login_no_users(client):
    """Login should fail when no users exist with given credentials."""
    resp = await client.post("/auth/login", json={"username": "nonexistent", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_success(client, admin_user):
    """Login with correct password returns a token."""
    resp = await client.post(
        "/auth/login",
        json={"username": admin_user["user"].username, "password": "admin-password-123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"].startswith("ns_")
    assert data["username"] == admin_user["user"].username
    assert data["role"] == "admin"
    assert data["expires_at"] is not None  # login tokens expire


@pytest.mark.asyncio
async def test_login_wrong_password(client, admin_user):
    """Login with wrong password returns 401."""
    resp = await client.post(
        "/auth/login",
        json={"username": admin_user["user"].username, "password": "wrong-password"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_user_as_admin(client, admin_user):
    """Admin can create new users."""
    resp = await client.post(
        "/auth/users",
        json={
            "username": f"newuser-{uuid4().hex[:8]}",
            "password": "password-123",
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_user['raw_key']}"},
    )
    # Auth is disabled by default, so this should work even without a token
    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == "viewer"


@pytest.mark.asyncio
async def test_create_api_key(client, admin_user):
    """Authenticated user can create an API key."""
    resp = await client.post(
        "/auth/api-keys",
        json={"label": "test-key"},
        headers={"Authorization": f"Bearer {admin_user['raw_key']}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"].startswith("ns_")
    assert data["label"] == "test-key"


@pytest.mark.asyncio
async def test_list_api_keys(client, admin_user):
    """Authenticated user can list their API keys."""
    resp = await client.get(
        "/auth/api-keys",
        headers={"Authorization": f"Bearer {admin_user['raw_key']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_delete_api_key(client, admin_user):
    """User can delete their own API key."""
    # Create a key to delete
    resp = await client.post(
        "/auth/api-keys",
        json={"label": "to-delete"},
        headers={"Authorization": f"Bearer {admin_user['raw_key']}"},
    )
    key_id = resp.json()["id"]

    resp = await client.delete(
        f"/auth/api-keys/{key_id}",
        headers={"Authorization": f"Bearer {admin_user['raw_key']}"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_duplicate_username_rejected(client, admin_user):
    """Creating a user with an existing username returns 409."""
    resp = await client.post(
        "/auth/users",
        json={
            "username": admin_user["user"].username,
            "password": "password-123",
            "role": "viewer",
        },
        headers={"Authorization": f"Bearer {admin_user['raw_key']}"},
    )
    assert resp.status_code == 409
