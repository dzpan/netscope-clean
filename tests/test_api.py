"""FastAPI endpoint smoke tests using httpx."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.models import DeviceStatus, TopologyResult
from backend.store import store


@pytest.fixture
async def sample_session():
    from backend.models import Device, Link

    result = TopologyResult(
        session_id="test-session-1234",
        discovered_at=datetime.now(UTC),
        devices=[
            Device(
                id="SW-CORE-01",
                hostname="SW-CORE-01",
                mgmt_ip="10.0.0.1",
                platform="C9200L-48P",
                status=DeviceStatus.OK,
            ),
            Device(
                id="SW-ACCESS-01",
                hostname="SW-ACCESS-01",
                mgmt_ip="10.0.0.2",
                status=DeviceStatus.PLACEHOLDER,
            ),
        ],
        links=[
            Link(
                source="SW-CORE-01",
                target="SW-ACCESS-01",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet0/1",
                protocol="CDP",
            )
        ],
        failures=[],
    )
    await store.save(result)
    return result


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_sessions_empty(client):
    # May not be empty if other tests ran first, but should be 200
    resp = await client.get("/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_session_not_found(client):
    resp = await client.get("/sessions/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_found(client, sample_session):
    resp = await client.get(f"/sessions/{sample_session.session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sample_session.session_id
    assert len(data["devices"]) == 2
    assert len(data["links"]) == 1


@pytest.mark.asyncio
async def test_export_drawio(client, sample_session):
    resp = await client.get(f"/export/{sample_session.session_id}/drawio")
    assert resp.status_code == 200
    assert "mxGraphModel" in resp.text
    assert "SW-CORE-01" in resp.text


@pytest.mark.asyncio
async def test_export_csv(client, sample_session):
    resp = await client.get(f"/export/{sample_session.session_id}/csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_export_excel(client, sample_session):
    resp = await client.get(f"/export/{sample_session.session_id}/excel")
    assert resp.status_code == 200
    ct = resp.headers["content-type"]
    assert "spreadsheetml" in ct or "officedocument" in ct
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_export_dot(client, sample_session):
    resp = await client.get(f"/export/{sample_session.session_id}/dot")
    assert resp.status_code == 200
    assert "graph topology" in resp.text
    assert "SW-CORE-01" in resp.text
    assert "SW-ACCESS-01" in resp.text


@pytest.mark.asyncio
async def test_export_json(client, sample_session):
    resp = await client.get(f"/export/{sample_session.session_id}/json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sample_session.session_id
    assert len(data["devices"]) == 2


@pytest.mark.asyncio
async def test_export_not_found(client):
    resp = await client.get("/export/bad-id/drawio")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_discover_validation(client):
    """POST /discover with missing fields should return 422."""
    resp = await client.post("/discover", json={})
    assert resp.status_code == 422
