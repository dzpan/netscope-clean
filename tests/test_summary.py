"""Tests for discovery summary and placeholder resolution endpoints."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.models import (
    Device,
    DeviceStatus,
    Failure,
    InterfaceInfo,
    Link,
    NativeVlanMismatch,
    STPVlanInfo,
    TopologyResult,
    VlanInfo,
)
from backend.store import store


@pytest.fixture
async def session_with_details():
    """Session with devices, placeholders, failures, VLANs, STP, etc."""
    result = TopologyResult(
        session_id="summary-test-001",
        discovered_at=datetime.now(UTC),
        devices=[
            Device(
                id="SW-CORE-01",
                hostname="SW-CORE-01",
                mgmt_ip="10.0.0.1",
                platform="C9200L-48P",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(name="Gi1/0/1", status="up", vlan="trunk"),
                    InterfaceInfo(name="Gi1/0/2", status="up", vlan="10"),
                    InterfaceInfo(name="Gi1/0/3", status="down", vlan="20"),
                ],
                vlans=[
                    VlanInfo(vlan_id="1", name="default"),
                    VlanInfo(vlan_id="10", name="Data"),
                    VlanInfo(vlan_id="20", name="Voice"),
                ],
                stp_info=[
                    STPVlanInfo(vlan_id="1", is_root=True),
                    STPVlanInfo(vlan_id="10", is_root=False),
                ],
            ),
            Device(
                id="SW-ACCESS-01",
                hostname="SW-ACCESS-01",
                mgmt_ip="10.0.0.2",
                platform="C9200L-24P",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(name="Gi1/0/1", status="up", vlan="trunk"),
                    InterfaceInfo(name="Gi1/0/2", status="up", vlan="10"),
                ],
                vlans=[
                    VlanInfo(vlan_id="10", name="Data"),
                ],
            ),
            Device(
                id="PLACEHOLDER-01",
                hostname="PLACEHOLDER-01",
                mgmt_ip="10.0.0.3",
                platform="Unknown",
                status=DeviceStatus.PLACEHOLDER,
            ),
        ],
        links=[
            Link(
                source="SW-CORE-01",
                target="SW-ACCESS-01",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet1/0/1",
                protocol="CDP",
            ),
            Link(
                source="SW-CORE-01",
                target="PLACEHOLDER-01",
                source_intf="GigabitEthernet1/0/24",
                target_intf="GigabitEthernet0/1",
                protocol="LLDP",
            ),
        ],
        failures=[
            Failure(target="10.0.0.99", reason="timeout", detail="Connection timed out"),
            Failure(target="10.0.0.100", reason="auth_failed", detail="Bad credentials"),
            Failure(target="10.0.0.101", reason="auth_failed", detail="Bad credentials"),
        ],
        native_vlan_mismatches=[
            NativeVlanMismatch(
                source="SW-CORE-01",
                target="SW-ACCESS-01",
                source_intf="Gi1/0/1",
                target_intf="Gi1/0/1",
                source_native_vlan="1",
                target_native_vlan="10",
            )
        ],
    )
    await store.save(result)
    return result


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.mark.asyncio
async def test_get_summary(client, session_with_details):
    resp = await client.get(f"/sessions/{session_with_details.session_id}/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert data["session_id"] == "summary-test-001"
    assert data["total_devices"] == 3
    assert data["ok_devices"] == 2
    assert data["placeholder_devices"] == 1
    assert data["total_failures"] == 3
    assert data["total_links"] == 2
    assert data["total_vlans"] == 3  # VLANs 1, 10, 20
    assert data["native_vlan_mismatches"] == 1
    assert data["stp_root_bridges"] == 1
    assert data["total_interfaces"] == 5  # 3 + 2 from OK devices
    assert data["up_interfaces"] == 4
    assert data["down_interfaces"] == 1

    # Check breakdowns
    failure_reasons = {f["reason"]: f["count"] for f in data["failure_breakdown"]}
    assert failure_reasons["auth_failed"] == 2
    assert failure_reasons["timeout"] == 1

    platforms = {p["platform"]: p["count"] for p in data["platform_breakdown"]}
    assert platforms["C9200L-48P"] == 1
    assert platforms["C9200L-24P"] == 1

    protocols = {p["protocol"]: p["count"] for p in data["protocol_breakdown"]}
    assert protocols["CDP"] == 1
    assert protocols["LLDP"] == 1


@pytest.mark.asyncio
async def test_summary_404(client):
    resp = await client.get("/sessions/nonexistent-session/summary")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_placeholder_updates_ip(client, session_with_details):
    resp = await client.post(
        f"/sessions/{session_with_details.session_id}/resolve-placeholder",
        json={
            "placeholder_device_id": "PLACEHOLDER-01",
            "mgmt_ip": "10.0.0.50",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Placeholder should still exist but with updated IP (no matching real device)
    placeholder = next((d for d in data["devices"] if d["id"] == "PLACEHOLDER-01"), None)
    assert placeholder is not None
    assert placeholder["mgmt_ip"] == "10.0.0.50"
    assert placeholder["status"] == "placeholder"


@pytest.mark.asyncio
async def test_resolve_placeholder_merges_with_real(client, session_with_details):
    """When placeholder IP matches a real device, reconciliation should merge them."""
    resp = await client.post(
        f"/sessions/{session_with_details.session_id}/resolve-placeholder",
        json={
            "placeholder_device_id": "PLACEHOLDER-01",
            "mgmt_ip": "10.0.0.1",  # matches SW-CORE-01
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Placeholder should be removed (merged into SW-CORE-01)
    ids = [d["id"] for d in data["devices"]]
    assert "PLACEHOLDER-01" not in ids
    assert "SW-CORE-01" in ids
    # Link should be rewritten to point at SW-CORE-01
    targets = [lk["target"] for lk in data["links"]]
    assert "PLACEHOLDER-01" not in targets


@pytest.mark.asyncio
async def test_resolve_placeholder_not_found(client, session_with_details):
    resp = await client.post(
        f"/sessions/{session_with_details.session_id}/resolve-placeholder",
        json={
            "placeholder_device_id": "NONEXISTENT",
            "mgmt_ip": "10.0.0.99",
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_non_placeholder_rejected(client, session_with_details):
    resp = await client.post(
        f"/sessions/{session_with_details.session_id}/resolve-placeholder",
        json={
            "placeholder_device_id": "SW-CORE-01",
            "mgmt_ip": "10.0.0.99",
        },
    )
    assert resp.status_code == 400
    assert "not a placeholder" in resp.json()["detail"]
