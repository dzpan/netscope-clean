"""Unit tests for discovery helper functions (no SSH required)."""

from __future__ import annotations

from backend.discovery import _backfill_platform_from_neighbors, _detect_native_vlan_mismatches
from backend.models import Device, DeviceStatus, Link, NeighborRecord, TrunkInfo


def _make_device(device_id: str, trunk_info: dict[str, TrunkInfo]) -> Device:
    return Device(id=device_id, mgmt_ip="0.0.0.0", status=DeviceStatus.OK, trunk_info=trunk_info)


def _make_link(src: str, src_intf: str, tgt: str, tgt_intf: str) -> Link:
    return Link(source=src, target=tgt, source_intf=src_intf, target_intf=tgt_intf, protocol="CDP")


# ---------------------------------------------------------------------------
# _detect_native_vlan_mismatches
# ---------------------------------------------------------------------------


def test_no_mismatch_same_native_vlan() -> None:
    sw1 = _make_device("SW1", {"Gi1/0/1": TrunkInfo(native_vlan="1", status="trunking")})
    sw2 = _make_device("SW2", {"Gi1/0/2": TrunkInfo(native_vlan="1", status="trunking")})
    link = _make_link("SW1", "Gi1/0/1", "SW2", "Gi1/0/2")
    result = _detect_native_vlan_mismatches([sw1, sw2], [link])
    assert result == []


def test_detects_native_vlan_mismatch() -> None:
    sw1 = _make_device("SW1", {"Gi1/0/1": TrunkInfo(native_vlan="1", status="trunking")})
    sw2 = _make_device("SW2", {"Gi1/0/2": TrunkInfo(native_vlan="10", status="trunking")})
    link = _make_link("SW1", "Gi1/0/1", "SW2", "Gi1/0/2")
    result = _detect_native_vlan_mismatches([sw1, sw2], [link])
    assert len(result) == 1
    m = result[0]
    assert m.source == "SW1"
    assert m.target == "SW2"
    assert m.source_native_vlan == "1"
    assert m.target_native_vlan == "10"


def test_no_mismatch_when_trunk_info_missing() -> None:
    """If one end has no trunk data, no mismatch is reported."""
    sw1 = _make_device("SW1", {"Gi1/0/1": TrunkInfo(native_vlan="1")})
    sw2 = _make_device("SW2", {})  # no trunk data collected
    link = _make_link("SW1", "Gi1/0/1", "SW2", "Gi1/0/2")
    result = _detect_native_vlan_mismatches([sw1, sw2], [link])
    assert result == []


def test_no_mismatch_when_native_vlan_none() -> None:
    """If native_vlan is None on either end, no mismatch is reported."""
    sw1 = _make_device("SW1", {"Gi1/0/1": TrunkInfo(native_vlan=None)})
    sw2 = _make_device("SW2", {"Gi1/0/2": TrunkInfo(native_vlan="10")})
    link = _make_link("SW1", "Gi1/0/1", "SW2", "Gi1/0/2")
    result = _detect_native_vlan_mismatches([sw1, sw2], [link])
    assert result == []


def test_normalizes_abbreviated_interface_names() -> None:
    """Link intf 'GigabitEthernet1/0/1' should match trunk key 'Gi1/0/1'."""
    sw1 = _make_device("SW1", {"Gi1/0/1": TrunkInfo(native_vlan="1")})
    sw2 = _make_device("SW2", {"Gi1/0/2": TrunkInfo(native_vlan="99")})
    # Link uses full interface names (as CDP may report them)
    link = _make_link("SW1", "GigabitEthernet1/0/1", "SW2", "GigabitEthernet1/0/2")
    result = _detect_native_vlan_mismatches([sw1, sw2], [link])
    assert len(result) == 1
    assert result[0].source_native_vlan == "1"
    assert result[0].target_native_vlan == "99"


def test_multiple_mismatches_across_links() -> None:
    sw1 = _make_device(
        "SW1",
        {
            "Gi1/0/1": TrunkInfo(native_vlan="1"),
            "Gi1/0/2": TrunkInfo(native_vlan="10"),
        },
    )
    sw2 = _make_device("SW2", {"Gi2/0/1": TrunkInfo(native_vlan="2")})
    sw3 = _make_device("SW3", {"Gi3/0/1": TrunkInfo(native_vlan="1")})
    links = [
        _make_link("SW1", "Gi1/0/1", "SW2", "Gi2/0/1"),  # 1 vs 2 → mismatch
        _make_link("SW1", "Gi1/0/2", "SW3", "Gi3/0/1"),  # 10 vs 1 → mismatch
    ]
    result = _detect_native_vlan_mismatches([sw1, sw2, sw3], links)
    assert len(result) == 2


def test_no_mismatches_with_empty_links() -> None:
    sw1 = _make_device("SW1", {"Gi1/0/1": TrunkInfo(native_vlan="1")})
    result = _detect_native_vlan_mismatches([sw1], [])
    assert result == []


def test_mismatch_fields_are_correct() -> None:
    sw1 = _make_device("SW1", {"Gi1/0/1": TrunkInfo(native_vlan="5")})
    sw2 = _make_device("SW2", {"Gi1/0/2": TrunkInfo(native_vlan="99")})
    link = _make_link("SW1", "Gi1/0/1", "SW2", "Gi1/0/2")
    result = _detect_native_vlan_mismatches([sw1, sw2], [link])
    assert len(result) == 1
    m = result[0]
    assert m.source == "SW1"
    assert m.target == "SW2"
    assert m.source_intf == "Gi1/0/1"
    assert m.target_intf == "Gi1/0/2"
    assert m.source_native_vlan == "5"
    assert m.target_native_vlan == "99"


# ---------------------------------------------------------------------------
# _backfill_platform_from_neighbors
# ---------------------------------------------------------------------------


def test_backfill_platform_from_cdp_neighbor() -> None:
    """C1200 with no platform gets backfilled from CDP neighbor data."""
    c1200 = Device(
        id="sw-zupanc-02",
        hostname="sw-zupanc-02",
        mgmt_ip="192.168.30.3",
        platform=None,
        status=DeviceStatus.OK,
    )
    neighbors = [
        NeighborRecord(
            device_id="sw-zupanc-02",
            ip_address="192.168.30.3",
            local_interface="Gi1/0/3",
            remote_interface="gi1",
            platform="cisco C1200-8T-E-2G",
            protocol="CDP",
        ),
    ]
    devices = [c1200]
    _backfill_platform_from_neighbors(devices, neighbors)
    assert devices[0].platform == "cisco C1200-8T-E-2G"


def test_backfill_does_not_overwrite_existing_platform() -> None:
    """Devices that already have a platform should not be changed."""
    sw = Device(
        id="SW-ACCESS-01",
        hostname="SW-ACCESS-01",
        mgmt_ip="10.0.0.1",
        platform="C9200L-48PXG-4X",
        status=DeviceStatus.OK,
    )
    neighbors = [
        NeighborRecord(
            device_id="SW-ACCESS-01",
            ip_address="10.0.0.1",
            local_interface="Gi1/0/1",
            remote_interface="Gi1/0/2",
            platform="cisco C9200-24T",
            protocol="CDP",
        ),
    ]
    devices = [sw]
    _backfill_platform_from_neighbors(devices, neighbors)
    assert devices[0].platform == "C9200L-48PXG-4X"


def test_backfill_no_neighbors_is_noop() -> None:
    """No crash when neighbor list is empty."""
    dev = Device(id="X", mgmt_ip="1.1.1.1", platform=None, status=DeviceStatus.OK)
    _backfill_platform_from_neighbors([dev], [])
    assert dev.platform is None


def test_backfill_matches_by_hostname() -> None:
    """Backfill should also match on hostname field."""
    dev = Device(
        id="some-mac-id",
        hostname="sw-zupanc-03",
        mgmt_ip="192.168.30.4",
        platform=None,
        status=DeviceStatus.OK,
    )
    neighbors = [
        NeighborRecord(
            device_id="sw-zupanc-03",
            ip_address="192.168.30.4",
            local_interface="Gi1/0/4",
            remote_interface="gi2",
            platform="cisco C1200-8T-E-2G",
            protocol="CDP",
        ),
    ]
    _backfill_platform_from_neighbors([dev], neighbors)
    assert dev.platform == "cisco C1200-8T-E-2G"


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


async def test_discovery_all_seeds_unreachable(mock_scrapli: type) -> None:
    """All seed IPs unreachable — result should have only failures, no devices."""
    from backend.discovery import run_discovery
    from backend.models import DiscoverRequest

    req = DiscoverRequest(
        seeds=["192.168.99.1", "192.168.99.2"],
        username="admin",
        password="wrong",
    )
    result = await run_discovery(req)
    assert len(result.devices) == 0
    assert len(result.failures) >= 1


async def test_discovery_partial_failure(mock_scrapli: type) -> None:
    """Some seeds reachable, some not — result has both devices and failures."""
    from backend.discovery import run_discovery
    from backend.models import DiscoverRequest
    from tests.fixtures.cli_outputs import VALID_PASSWORD, VALID_USERNAME

    # First seed is valid (in DEVICE_REGISTRY), second is unreachable
    req = DiscoverRequest(
        seeds=["10.0.0.1", "192.168.99.99"],
        username=VALID_USERNAME,
        password=VALID_PASSWORD,
        max_hops=0,  # Don't BFS beyond seeds
    )
    result = await run_discovery(req)
    assert len(result.devices) >= 1
    assert len(result.failures) >= 1
