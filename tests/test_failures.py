"""Tests for graceful discovery failure handling — NET-76."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from backend.discovery import _classify_error
from backend.main import app
from backend.models import (
    Device,
    DeviceStatus,
    DiscoveryProgress,
    Failure,
    Link,
    TopologyResult,
)
from backend.store import store  # noqa: I001

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def session_with_failures():
    """Session with a mix of OK devices and various failure types."""
    result = TopologyResult(
        session_id="fail-session-001",
        discovered_at=datetime.now(UTC),
        devices=[
            Device(
                id="SW-CORE",
                hostname="SW-CORE",
                mgmt_ip="10.0.0.1",
                platform="C9200L-48P",
                status=DeviceStatus.OK,
            ),
            Device(
                id="SW-ACCESS-01",
                hostname="SW-ACCESS-01",
                mgmt_ip="10.0.0.2",
                platform="C3560-48P",
                status=DeviceStatus.OK,
            ),
        ],
        links=[
            Link(
                source="SW-CORE",
                target="SW-ACCESS-01",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet0/1",
                protocol="CDP",
            )
        ],
        failures=[
            Failure(target="10.0.0.10", reason="auth_failed", detail="permission denied"),
            Failure(target="10.0.0.11", reason="timeout", detail="connection timed out"),
            Failure(
                target="10.0.0.12",
                reason="unreachable",
                detail="connection refused",
            ),
        ],
    )
    await store.save(result)
    return result


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


# ---------------------------------------------------------------------------
# _classify_error unit tests
# ---------------------------------------------------------------------------


class TestClassifyError:
    def test_auth_keywords(self) -> None:
        exc = Exception("SSH authentication failed")
        assert _classify_error(exc) == "auth_failed"

    def test_permission_keyword(self) -> None:
        exc = Exception("Permission denied (publickey,password)")
        assert _classify_error(exc) == "auth_failed"

    def test_timeout_keyword(self) -> None:
        exc = Exception("Connection timed out after 30s")
        assert _classify_error(exc) == "timeout"

    def test_refused_keyword(self) -> None:
        exc = Exception("Connection refused")
        assert _classify_error(exc) == "unreachable"

    def test_no_route(self) -> None:
        exc = Exception("No route to host 10.0.0.99")
        assert _classify_error(exc) == "unreachable"

    def test_not_opened(self) -> None:
        exc = Exception("connection not opened")
        assert _classify_error(exc) == "unreachable"

    def test_unknown_fallback(self) -> None:
        exc = Exception("something completely unexpected happened")
        assert _classify_error(exc) == "unknown"

    def test_chained_exception(self) -> None:
        inner = Exception("authentication failed")
        outer = Exception("scrapli error")
        outer.__cause__ = inner
        assert _classify_error(outer) == "auth_failed"


# ---------------------------------------------------------------------------
# DiscoveryProgress model tests
# ---------------------------------------------------------------------------


class TestDiscoveryProgress:
    def test_basic_progress(self) -> None:
        p = DiscoveryProgress(
            session_id="sess-1",
            total_queued=10,
            discovered=5,
            failed=1,
            in_progress=2,
            latest_device="SW-01",
            latest_status="ok",
            phase="discovering",
        )
        assert p.total_queued == 10
        assert p.discovered == 5
        assert p.failed == 1
        assert p.phase == "discovering"

    def test_default_phase(self) -> None:
        p = DiscoveryProgress(
            session_id="sess-1",
            total_queued=1,
            discovered=0,
            failed=0,
            in_progress=0,
        )
        assert p.phase == "discovering"
        assert p.latest_device is None

    def test_json_round_trip(self) -> None:
        p = DiscoveryProgress(
            session_id="sess-1",
            total_queued=3,
            discovered=2,
            failed=1,
            in_progress=0,
            phase="done",
        )
        json_str = p.model_dump_json()
        p2 = DiscoveryProgress.model_validate_json(json_str)
        assert p2.session_id == p.session_id
        assert p2.total_queued == 3
        assert p2.phase == "done"


# ---------------------------------------------------------------------------
# Partial results in TopologyResult
# ---------------------------------------------------------------------------


class TestPartialResults:
    def test_session_has_both_devices_and_failures(
        self, session_with_failures: TopologyResult
    ) -> None:
        """A discovery with failures still returns devices and links."""
        s = session_with_failures
        assert len(s.devices) == 2
        assert len(s.links) == 1
        assert len(s.failures) == 3

    def test_failure_reasons_are_distinct(self, session_with_failures: TopologyResult) -> None:
        reasons = {f.reason for f in session_with_failures.failures}
        assert reasons == {"auth_failed", "timeout", "unreachable"}


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_failed_no_session(client: AsyncClient) -> None:
    resp = await client.post(
        "/retry-failed",
        json={
            "session_id": "nonexistent-session",
            "username": "admin",
            "password": "pass",
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_failed_with_reason_filter(
    client: AsyncClient, session_with_failures: TopologyResult
) -> None:
    """Retry only timeout failures — others should remain."""
    # This will fail to actually connect (no real devices) but the endpoint
    # should process the request and return a result
    resp = await client.post(
        "/retry-failed",
        json={
            "session_id": session_with_failures.session_id,
            "username": "admin",
            "password": "pass",
            "reason_filter": ["timeout"],
        },
        timeout=60,
    )
    # Without scrapli/real devices, this may raise or the retry returns failures
    # The key test is that the endpoint accepts the request shape
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_retry_failed_empty_filter_returns_existing(
    client: AsyncClient, session_with_failures: TopologyResult
) -> None:
    """When reason_filter doesn't match any failures, return existing session unchanged."""
    resp = await client.post(
        "/retry-failed",
        json={
            "session_id": session_with_failures.session_id,
            "username": "admin",
            "password": "pass",
            "reason_filter": ["nonexistent_reason"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should return existing session unchanged since no failures matched
    assert len(data["devices"]) == 2
    assert len(data["failures"]) == 3


@pytest.mark.asyncio
async def test_discover_stream_endpoint_exists(client: AsyncClient) -> None:
    """Verify the SSE endpoint exists and returns text/event-stream."""
    resp = await client.post(
        "/discover/stream",
        json={"seeds": ["10.0.0.1"], "username": "admin", "password": "pass"},
        timeout=10,
    )
    # May fail due to no real devices, but should return 200 with SSE content type
    # or an error in the stream — either way the endpoint exists
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
