"""Tests for the topology diff engine."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from backend.diff import compute_diff
from backend.models import (
    Device,
    DeviceStatus,
    Failure,
    Link,
    TopologyResult,
)


def _ts() -> datetime:
    return datetime.now(UTC)


def _session(
    devices: list[Device],
    links: list[Link] | None = None,
    failures: list[Failure] | None = None,
) -> TopologyResult:
    return TopologyResult(
        session_id=str(uuid4()),
        discovered_at=_ts(),
        devices=devices,
        links=links or [],
        failures=failures or [],
    )


def _device(
    device_id: str,
    hostname: str | None = None,
    status: DeviceStatus = DeviceStatus.OK,
    platform: str | None = None,
    os_version: str | None = None,
) -> Device:
    return Device(
        id=device_id,
        hostname=hostname or device_id,
        mgmt_ip=f"10.0.0.{abs(hash(device_id)) % 254 + 1}",
        status=status,
        platform=platform,
        os_version=os_version,
    )


def _link(source: str, target: str, s_intf: str = "Gi1/0/1", t_intf: str = "Gi1/0/1") -> Link:
    return Link(
        source=source, target=target, source_intf=s_intf, target_intf=t_intf, protocol="CDP"
    )


# ---------------------------------------------------------------------------
# No-change baseline
# ---------------------------------------------------------------------------


class TestNoDiff:
    def test_identical_topologies_produce_zero_changes(self) -> None:
        sw1 = _device("SW1", platform="Cisco Catalyst 9300")
        sw2 = _device("SW2")
        link = _link("SW1", "SW2")
        prev = _session([sw1, sw2], [link])
        curr = _session([sw1, sw2], [link])
        diff = compute_diff(curr, prev)
        assert diff.total_changes == 0
        assert diff.devices_added == []
        assert diff.devices_removed == []
        assert diff.devices_changed == []
        assert diff.links_added == []
        assert diff.links_removed == []

    def test_diff_ids_set_correctly(self) -> None:
        prev = _session([_device("SW1")])
        curr = _session([_device("SW1")])
        diff = compute_diff(curr, prev)
        assert diff.current_session_id == curr.session_id
        assert diff.previous_session_id == prev.session_id


# ---------------------------------------------------------------------------
# Device-level changes
# ---------------------------------------------------------------------------


class TestDeviceChanges:
    def test_device_added(self) -> None:
        sw1 = _device("SW1")
        sw2 = _device("SW2")
        prev = _session([sw1])
        curr = _session([sw1, sw2])
        diff = compute_diff(curr, prev)
        assert "SW2" in diff.devices_added
        assert diff.devices_removed == []
        assert diff.total_changes == 1

    def test_device_removed(self) -> None:
        sw1 = _device("SW1")
        sw2 = _device("SW2")
        prev = _session([sw1, sw2])
        curr = _session([sw1])
        diff = compute_diff(curr, prev)
        assert "SW2" in diff.devices_removed
        assert diff.devices_added == []
        assert diff.total_changes == 1

    def test_device_status_changed(self) -> None:
        sw1_ok = _device("SW1", status=DeviceStatus.OK)
        sw1_unreach = _device("SW1", status=DeviceStatus.UNREACHABLE)
        prev = _session([sw1_ok])
        curr = _session([sw1_unreach])
        diff = compute_diff(curr, prev)
        assert len(diff.devices_changed) == 1
        changed = diff.devices_changed[0]
        assert changed.device_id == "SW1"
        assert any(c.field == "status" for c in changed.changes)
        status_change = next(c for c in changed.changes if c.field == "status")
        assert status_change.before == "ok"
        assert status_change.after == "unreachable"

    def test_device_platform_changed(self) -> None:
        sw1_old = _device("SW1", platform="Cisco Catalyst 3850")
        sw1_new = _device("SW1", platform="Cisco Catalyst 9300")
        prev = _session([sw1_old])
        curr = _session([sw1_new])
        diff = compute_diff(curr, prev)
        assert len(diff.devices_changed) == 1
        chg = diff.devices_changed[0]
        plat = next(c for c in chg.changes if c.field == "platform")
        assert plat.before == "Cisco Catalyst 3850"
        assert plat.after == "Cisco Catalyst 9300"

    def test_multiple_field_changes_on_same_device(self) -> None:
        sw1_old = _device("SW1", platform="OLD-PLATFORM", os_version="16.0.1")
        sw1_new = _device("SW1", platform="NEW-PLATFORM", os_version="17.3.2")
        prev = _session([sw1_old])
        curr = _session([sw1_new])
        diff = compute_diff(curr, prev)
        assert len(diff.devices_changed) == 1
        fields = {c.field for c in diff.devices_changed[0].changes}
        assert {"platform", "os_version"}.issubset(fields)

    def test_unchanged_device_not_in_devices_changed(self) -> None:
        sw1 = _device("SW1", platform="Same")
        sw2_old = _device("SW2", os_version="16.0")
        sw2_new = _device("SW2", os_version="17.0")
        prev = _session([sw1, sw2_old])
        curr = _session([sw1, sw2_new])
        diff = compute_diff(curr, prev)
        assert all(d.device_id == "SW2" for d in diff.devices_changed)


# ---------------------------------------------------------------------------
# Link-level changes
# ---------------------------------------------------------------------------


class TestLinkChanges:
    def test_link_added(self) -> None:
        sw1 = _device("SW1")
        sw2 = _device("SW2")
        sw3 = _device("SW3")
        old_link = _link("SW1", "SW2")
        new_link = _link("SW1", "SW3", "Gi1/0/2", "Gi1/0/1")
        prev = _session([sw1, sw2, sw3], [old_link])
        curr = _session([sw1, sw2, sw3], [old_link, new_link])
        diff = compute_diff(curr, prev)
        assert len(diff.links_added) == 1
        assert diff.links_removed == []
        added = diff.links_added[0]
        assert {added.source, added.target} == {"SW1", "SW3"}

    def test_link_removed(self) -> None:
        sw1 = _device("SW1")
        sw2 = _device("SW2")
        link = _link("SW1", "SW2")
        prev = _session([sw1, sw2], [link])
        curr = _session([sw1, sw2], [])
        diff = compute_diff(curr, prev)
        assert len(diff.links_removed) == 1
        assert diff.links_added == []

    def test_link_key_is_direction_agnostic(self) -> None:
        """A→B and B→A should be treated as the same link."""
        sw1 = _device("SW1")
        sw2 = _device("SW2")
        link_fwd = _link("SW1", "SW2", "Gi1/0/1", "Gi1/0/1")
        link_rev = _link("SW2", "SW1", "Gi1/0/1", "Gi1/0/1")
        prev = _session([sw1, sw2], [link_fwd])
        curr = _session([sw1, sw2], [link_rev])
        diff = compute_diff(curr, prev)
        # Same canonical key → no change
        assert diff.links_added == []
        assert diff.links_removed == []
        assert diff.total_changes == 0


# ---------------------------------------------------------------------------
# Mixed / combined changes
# ---------------------------------------------------------------------------


class TestCombinedChanges:
    def test_total_changes_is_sum_of_all_categories(self) -> None:
        sw1 = _device("SW1")
        sw2 = _device("SW2")
        sw3_old = _device("SW3", os_version="16.0")
        sw3_new = _device("SW3", os_version="17.0")
        sw4 = _device("SW4")
        old_link = _link("SW1", "SW2")
        new_link = _link("SW1", "SW3", "Gi1/0/2", "Gi1/0/1")

        prev = _session([sw1, sw2, sw3_old], [old_link])
        curr = _session([sw1, sw3_new, sw4], [new_link])  # sw2 removed, sw4 added, sw3 changed

        diff = compute_diff(curr, prev)
        # sw2 removed=1, sw4 added=1, sw3 changed=1, old_link removed=1, new_link added=1
        assert diff.total_changes == 5

    def test_empty_to_populated(self) -> None:
        sw1 = _device("SW1")
        sw2 = _device("SW2")
        prev = _session([])
        curr = _session([sw1, sw2], [_link("SW1", "SW2")])
        diff = compute_diff(curr, prev)
        assert len(diff.devices_added) == 2
        assert len(diff.links_added) == 1
        assert diff.total_changes == 3

    def test_populated_to_empty(self) -> None:
        sw1 = _device("SW1")
        sw2 = _device("SW2")
        prev = _session([sw1, sw2], [_link("SW1", "SW2")])
        curr = _session([])
        diff = compute_diff(curr, prev)
        assert len(diff.devices_removed) == 2
        assert len(diff.links_removed) == 1
        assert diff.total_changes == 3
