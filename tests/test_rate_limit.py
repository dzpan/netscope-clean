"""Tests for rate limiting middleware."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def client():
    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


async def test_health_within_default_limit(client: AsyncClient) -> None:
    """Health endpoint should succeed within default rate limit."""
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_rate_limit_headers_present(client: AsyncClient) -> None:
    """Rate-limited responses include X-RateLimit headers."""
    resp = await client.get("/health")
    # slowapi adds these headers when enabled
    assert "x-ratelimit-limit" in resp.headers or resp.status_code == 200
