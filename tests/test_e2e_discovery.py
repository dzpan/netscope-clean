"""End-to-end integration tests for the full discovery pipeline.

Uses a mock Scrapli driver backed by canned CLI outputs to simulate a
7-device Cisco network topology without real SSH connections.

Topology:
    CORE-SW-01 ─── DIST-SW-01 ─── ACCESS-SW-01
                │              └── ACCESS-SW-02
                ├── DIST-SW-02 ─── ACCESS-SW-03
                └── ROUTER-01
"""

from __future__ import annotations

import pytest

from backend.discovery import run_discovery
from backend.models import (
    CollectionProfile,
    CredentialSet,
    DeviceStatus,
    DiscoverRequest,
    DiscoveryProgress,
    DiscoveryProtocol,
)
from backend.store import store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_request(**overrides: object) -> DiscoverRequest:
    """Build a DiscoverRequest with good defaults for the mock topology."""
    defaults: dict[str, object] = {
        "seeds": ["10.0.0.1"],
        "username": "admin",
        "password": "cisco123",
        "max_hops": 4,
        "timeout": 30,
        "collection_profile": CollectionProfile.FULL,
    }
    defaults.update(overrides)
    return DiscoverRequest(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Full topology discovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_topology_discovery(mock_scrapli: object, clean_store: None) -> None:
    """BFS from CORE-SW-01 should discover all 7 devices in the topology."""
    req = _base_request()
    result = await run_discovery(req)

    device_names = {d.hostname for d in result.devices if d.status == DeviceStatus.OK}
    assert "CORE-SW-01" in device_names
    assert "DIST-SW-01" in device_names
    assert "DIST-SW-02" in device_names
    assert "ACCESS-SW-01" in device_names
    assert "ACCESS-SW-02" in device_names
    assert "ACCESS-SW-03" in device_names
    assert "ROUTER-01" in device_names

    ok_devices = [d for d in result.devices if d.status == DeviceStatus.OK]
    assert len(ok_devices) == 7


@pytest.mark.asyncio
async def test_discovery_produces_links(mock_scrapli: object, clean_store: None) -> None:
    """All expected links should be present in the result."""
    req = _base_request()
    result = await run_discovery(req)

    # Build a set of (source, target) pairs (normalized to sorted tuple)
    link_pairs = set()
    for lk in result.links:
        pair = tuple(sorted([lk.source, lk.target]))
        link_pairs.add(pair)

    expected = {
        tuple(sorted(["CORE-SW-01", "DIST-SW-01"])),
        tuple(sorted(["CORE-SW-01", "DIST-SW-02"])),
        tuple(sorted(["CORE-SW-01", "ROUTER-01"])),
        tuple(sorted(["DIST-SW-01", "ACCESS-SW-01"])),
        tuple(sorted(["DIST-SW-01", "ACCESS-SW-02"])),
        tuple(sorted(["DIST-SW-02", "ACCESS-SW-03"])),
    }

    for pair in expected:
        assert pair in link_pairs, f"Missing link: {pair[0]} <-> {pair[1]}"


@pytest.mark.asyncio
async def test_discovery_session_persistence(mock_scrapli: object, clean_store: None) -> None:
    """After discovery, the result should be retrievable from the session store."""
    req = _base_request()
    result = await run_discovery(req)
    await store.save(result)

    stored = store.get(result.session_id)
    assert stored is not None
    assert stored.session_id == result.session_id
    assert len(stored.devices) == len(result.devices)


# ---------------------------------------------------------------------------
# Partial / scoped discovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_hops_limits_depth(mock_scrapli: object, clean_store: None) -> None:
    """With max_hops=1, only the seed and its direct neighbors are discovered."""
    req = _base_request(max_hops=1)
    result = await run_discovery(req)

    ok_names = {d.hostname for d in result.devices if d.status == DeviceStatus.OK}
    # Depth 0: CORE-SW-01, Depth 1: DIST-SW-01, DIST-SW-02, ROUTER-01
    assert "CORE-SW-01" in ok_names
    assert "DIST-SW-01" in ok_names
    assert "DIST-SW-02" in ok_names
    assert "ROUTER-01" in ok_names
    # Access switches are depth 2 — should NOT be fully discovered
    # (they may appear as placeholders but not OK)
    ok_access = {n for n in ok_names if n.startswith("ACCESS-")}
    assert len(ok_access) == 0


@pytest.mark.asyncio
async def test_scope_restricts_discovery(mock_scrapli: object, clean_store: None) -> None:
    """Scope=10.0.0.0/30 covers only .1-.3 so access switches are excluded."""
    req = _base_request(scope="10.0.0.0/30", max_hops=4)
    result = await run_discovery(req)

    ok_names = {d.hostname for d in result.devices if d.status == DeviceStatus.OK}
    assert "CORE-SW-01" in ok_names
    # /30 gives 10.0.0.0-10.0.0.3 — DIST-SW-01 (10.0.0.2) and DIST-SW-02 (10.0.0.3) in scope
    assert "DIST-SW-01" in ok_names
    assert "DIST-SW-02" in ok_names
    # 10.0.0.4-7 are out of scope
    assert "ROUTER-01" not in ok_names
    assert "ACCESS-SW-01" not in ok_names


# ---------------------------------------------------------------------------
# Credential handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_credentials_produce_failures(mock_scrapli: object, clean_store: None) -> None:
    """Bad creds should result in auth_failed failures, not crashes."""
    req = _base_request(username="wrong", password="bad", max_hops=0)
    result = await run_discovery(req)

    assert len(result.failures) > 0
    assert result.failures[0].reason == "auth_failed"
    assert len([d for d in result.devices if d.status == DeviceStatus.OK]) == 0


@pytest.mark.asyncio
async def test_multi_credential_rotation(mock_scrapli: object, clean_store: None) -> None:
    """First cred set fails auth, second succeeds — device should be discovered."""
    req = _base_request(
        username="",
        password="",
        credential_sets=[
            CredentialSet(username="wrong", password="bad", label="bad-creds"),
            CredentialSet(username="admin", password="cisco123", label="good-creds"),
        ],
        max_hops=0,
    )
    result = await run_discovery(req)

    ok_devices = [d for d in result.devices if d.status == DeviceStatus.OK]
    assert len(ok_devices) == 1
    assert ok_devices[0].hostname == "CORE-SW-01"


@pytest.mark.asyncio
async def test_unreachable_host(mock_scrapli: object, clean_store: None) -> None:
    """Connecting to an IP not in the registry should fail with 'unreachable'."""
    req = _base_request(seeds=["192.168.99.99"], max_hops=0)
    result = await run_discovery(req)

    assert len(result.failures) == 1
    assert result.failures[0].reason == "unreachable"


# ---------------------------------------------------------------------------
# Collection profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minimal_profile_skips_tables(mock_scrapli: object, clean_store: None) -> None:
    """MINIMAL profile collects only version + neighbors — no VLANs, ARP, etc."""
    req = _base_request(max_hops=0, collection_profile=CollectionProfile.MINIMAL)
    result = await run_discovery(req)

    core = next(d for d in result.devices if d.hostname == "CORE-SW-01")
    assert core.status == DeviceStatus.OK
    # Minimal: no interfaces, vlans, arp, mac collected
    assert len(core.interfaces) == 0
    assert len(core.vlans) == 0
    assert len(core.arp_table) == 0


@pytest.mark.asyncio
async def test_full_profile_collects_everything(mock_scrapli: object, clean_store: None) -> None:
    """FULL profile should populate interfaces, VLANs, ARP, routes, trunks."""
    req = _base_request(max_hops=0, collection_profile=CollectionProfile.FULL)
    result = await run_discovery(req)

    core = next(d for d in result.devices if d.hostname == "CORE-SW-01")
    assert core.status == DeviceStatus.OK
    assert len(core.interfaces) > 0
    assert len(core.vlans) > 0
    assert len(core.arp_table) > 0
    assert len(core.route_table) > 0
    assert len(core.trunk_info) > 0


# ---------------------------------------------------------------------------
# Data correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parsed_device_metadata(mock_scrapli: object, clean_store: None) -> None:
    """Verify parsed version info is correct for the core switch."""
    req = _base_request(max_hops=0)
    result = await run_discovery(req)

    core = next(d for d in result.devices if d.hostname == "CORE-SW-01")
    assert core.platform is not None
    assert "C9300" in core.platform
    assert core.os_version is not None
    assert "17.06.05" in core.os_version
    assert core.base_mac == "00aa.bbcc.dd01"


@pytest.mark.asyncio
async def test_parsed_vlan_data(mock_scrapli: object, clean_store: None) -> None:
    """VLANs should be parsed from show vlan brief output."""
    req = _base_request(max_hops=0, collection_profile=CollectionProfile.FULL)
    result = await run_discovery(req)

    core = next(d for d in result.devices if d.hostname == "CORE-SW-01")
    vlan_ids = {v.vlan_id for v in core.vlans}
    assert "1" in vlan_ids
    assert "10" in vlan_ids
    assert "20" in vlan_ids
    assert "30" in vlan_ids
    assert "99" in vlan_ids


@pytest.mark.asyncio
async def test_trunk_info_parsed(mock_scrapli: object, clean_store: None) -> None:
    """Trunk interfaces should have native VLAN data."""
    req = _base_request(max_hops=0, collection_profile=CollectionProfile.FULL)
    result = await run_discovery(req)

    core = next(d for d in result.devices if d.hostname == "CORE-SW-01")
    assert len(core.trunk_info) > 0
    # All CORE trunks have native VLAN 99
    for _port, info in core.trunk_info.items():
        assert info.native_vlan == "99"


@pytest.mark.asyncio
async def test_no_native_vlan_mismatches_in_topology(
    mock_scrapli: object, clean_store: None
) -> None:
    """All devices use native VLAN 99 — no mismatches expected."""
    req = _base_request(collection_profile=CollectionProfile.FULL)
    result = await run_discovery(req)
    assert len(result.native_vlan_mismatches) == 0


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_callback_fires(mock_scrapli: object, clean_store: None) -> None:
    """The progress callback should be called with valid DiscoveryProgress objects."""
    events: list[DiscoveryProgress] = []
    req = _base_request(max_hops=0)
    await run_discovery(req, progress_callback=events.append)

    assert len(events) > 0
    # Should have at least a "discovering" phase and end with "done"
    phases = [e.phase for e in events]
    assert "discovering" in phases
    assert phases[-1] in ("done", "finalizing")


# ---------------------------------------------------------------------------
# Discovery protocol selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cdp_prefer_protocol(mock_scrapli: object, clean_store: None) -> None:
    """CDP_PREFER should discover neighbors via CDP."""
    req = _base_request(max_hops=0, discovery_protocol=DiscoveryProtocol.CDP_PREFER)
    result = await run_discovery(req)
    ok = [d for d in result.devices if d.status == DeviceStatus.OK]
    assert len(ok) == 1
    # Core switch has 3 CDP neighbors
    assert len(result.links) == 3


@pytest.mark.asyncio
async def test_lldp_prefer_fallback_to_cdp(mock_scrapli: object, clean_store: None) -> None:
    """LLDP_PREFER with LLDP disabled should fall back to CDP and still find neighbors."""
    req = _base_request(max_hops=0, discovery_protocol=DiscoveryProtocol.LLDP_PREFER)
    result = await run_discovery(req)
    ok = [d for d in result.devices if d.status == DeviceStatus.OK]
    assert len(ok) == 1
    # Should fall back to CDP and find 3 neighbors
    assert len(result.links) == 3


# ---------------------------------------------------------------------------
# API endpoint integration (full stack)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_discover_endpoint(
    mock_scrapli: object, clean_store: None, async_client: object
) -> None:
    """POST /discover should return a complete TopologyResult."""
    resp = await async_client.post(  # type: ignore[union-attr]
        "/discover",
        json={
            "seeds": ["10.0.0.1"],
            "username": "admin",
            "password": "cisco123",
            "max_hops": 1,
            "collection_profile": "standard",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "devices" in data
    assert "links" in data
    # At least the seed + direct neighbors
    ok_devices = [d for d in data["devices"] if d["status"] == "ok"]
    assert len(ok_devices) >= 4


@pytest.mark.asyncio
async def test_api_sessions_round_trip(
    mock_scrapli: object, clean_store: None, async_client: object
) -> None:
    """Discover → list sessions → get session should all work."""
    # Discover
    resp = await async_client.post(  # type: ignore[union-attr]
        "/discover",
        json={
            "seeds": ["10.0.0.1"],
            "username": "admin",
            "password": "cisco123",
            "max_hops": 0,
        },
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    # List
    resp = await async_client.get("/sessions")  # type: ignore[union-attr]
    assert resp.status_code == 200
    ids = [s["session_id"] for s in resp.json()]
    assert session_id in ids

    # Get specific session
    resp = await async_client.get(f"/sessions/{session_id}")  # type: ignore[union-attr]
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_api_probe_endpoint(
    mock_scrapli: object, clean_store: None, async_client: object
) -> None:
    """POST /probe should verify connectivity to a simulated device."""
    resp = await async_client.post(  # type: ignore[union-attr]
        "/probe",
        json={
            "host": "10.0.0.1",
            "username": "admin",
            "password": "cisco123",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "CORE-SW-01" in (data.get("hostname") or "")
