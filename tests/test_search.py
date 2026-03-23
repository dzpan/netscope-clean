"""Tests for FTS5 search indexing and query functions."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from backend.models import (
    ArpEntry,
    Device,
    DeviceStatus,
    InterfaceInfo,
    MacTableEntry,
    RouteEntry,
    TopologyResult,
    VlanInfo,
)
from backend.search import (
    SEARCH_FTS_DDL,
    _fts_query,
    _mac_variants,
    _normalize_mac,
    build_search_index,
    search_in_memory,
    search_index,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SEARCH_FTS_DDL)
    conn.commit()
    return conn


def _make_result(session_id: str = "sess1") -> TopologyResult:
    return TopologyResult(
        session_id=session_id,
        discovered_at=datetime.now(UTC),
        devices=[
            Device(
                id="SW1",
                hostname="core-switch-01",
                mgmt_ip="10.0.0.1",
                platform="C9300-48P",
                serial="FCW1234A0BC",
                os_version="17.3.4",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="GigabitEthernet1/0/1",
                        description="Uplink to router",
                        ip_address="10.0.0.2",
                        status="connected",
                        vlan="10",
                    ),
                    InterfaceInfo(
                        name="GigabitEthernet1/0/2",
                        description="Server port",
                        status="notconnect",
                    ),
                ],
                vlans=[
                    VlanInfo(vlan_id="10", name="MGMT"),
                    VlanInfo(vlan_id="20", name="SERVERS"),
                ],
                arp_table=[
                    ArpEntry(
                        ip_address="192.168.1.100",
                        mac_address="aabb.ccdd.eeff",
                        interface="GigabitEthernet1/0/1",
                    ),
                ],
                mac_table=[
                    MacTableEntry(
                        mac_address="aabb.ccdd.eeff",
                        vlan_id="10",
                        interface="GigabitEthernet1/0/1",
                    ),
                ],
                route_table=[
                    RouteEntry(
                        destination="0.0.0.0/0",
                        next_hop="10.0.0.254",
                        route_type="static",
                    ),
                    RouteEntry(
                        destination="192.168.1.0/24",
                        route_type="connected",
                        interface="GigabitEthernet1/0/1",
                    ),
                ],
            ),
            Device(
                id="RTR1",
                hostname="edge-router",
                mgmt_ip="10.0.0.254",
                platform="ISR4451",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="GigabitEthernet0/0/0",
                        description="WAN link",
                        ip_address="203.0.113.1",
                        status="connected",
                    )
                ],
            ),
        ],
        links=[],
        failures=[],
    )


# ---------------------------------------------------------------------------
# MAC normalization helpers
# ---------------------------------------------------------------------------


class TestMacHelpers:
    def test_normalize_colon(self) -> None:
        assert _normalize_mac("aa:bb:cc:dd:ee:ff") == "aabbccddeeff"

    def test_normalize_cisco(self) -> None:
        assert _normalize_mac("aabb.ccdd.eeff") == "aabbccddeeff"

    def test_normalize_dash(self) -> None:
        assert _normalize_mac("aa-bb-cc-dd-ee-ff") == "aabbccddeeff"

    def test_normalize_uppercase(self) -> None:
        assert _normalize_mac("AA:BB:CC:DD:EE:FF") == "aabbccddeeff"

    def test_mac_variants_contains_all_formats(self) -> None:
        variants = _mac_variants("aabb.ccdd.eeff")
        assert "aabbccddeeff" in variants
        assert "aa:bb:cc:dd:ee:ff" in variants
        assert "aabb.ccdd.eeff" in variants
        assert "aa-bb-cc-dd-ee-ff" in variants


# ---------------------------------------------------------------------------
# FTS query builder
# ---------------------------------------------------------------------------


class TestFtsQuery:
    def test_simple_term(self) -> None:
        assert _fts_query("switch") == "switch*"

    def test_multi_word(self) -> None:
        q = _fts_query("core switch")
        assert "core*" in q
        assert "switch*" in q

    def test_ip_strips_dots(self) -> None:
        q = _fts_query("10.0.0.1")
        assert "10*" in q
        assert "0*" in q
        assert "1*" in q

    def test_mac_strips_delimiters(self) -> None:
        q = _fts_query("aabb.ccdd")
        assert "aabb*" in q
        assert "ccdd*" in q

    def test_empty(self) -> None:
        assert _fts_query("") == '""'


# ---------------------------------------------------------------------------
# FTS5 build + search
# ---------------------------------------------------------------------------


class TestFts5Search:
    def setup_method(self) -> None:
        self.conn = _make_db()
        self.result = _make_result()
        build_search_index(self.conn, self.result)

    def test_device_by_hostname(self) -> None:
        resp = search_index(self.conn, "core-switch")
        assert resp.total > 0
        device_hits = [h for h in resp.results if h.result_type == "device"]
        assert any("core-switch-01" in h.label for h in device_hits)

    def test_device_by_ip(self) -> None:
        resp = search_index(self.conn, "10.0.0.1")
        assert resp.total > 0
        assert any(h.device_id == "SW1" for h in resp.results)

    def test_device_by_platform(self) -> None:
        resp = search_index(self.conn, "C9300")
        assert resp.total > 0
        assert any(h.tab == "overview" for h in resp.results)

    def test_interface_by_description(self) -> None:
        resp = search_index(self.conn, "Uplink")
        intf_hits = [h for h in resp.results if h.result_type == "interface"]
        assert len(intf_hits) > 0
        assert any("GigabitEthernet1/0/1" in h.label for h in intf_hits)

    def test_interface_tab_hint(self) -> None:
        resp = search_index(self.conn, "GigabitEthernet1/0/1")
        assert any(h.tab == "interfaces" for h in resp.results)

    def test_vlan_by_id(self) -> None:
        resp = search_index(self.conn, "vlan10")
        vlan_hits = [h for h in resp.results if h.result_type == "vlan"]
        assert len(vlan_hits) > 0

    def test_vlan_by_name(self) -> None:
        resp = search_index(self.conn, "MGMT")
        vlan_hits = [h for h in resp.results if h.result_type == "vlan"]
        assert len(vlan_hits) > 0

    def test_arp_by_ip(self) -> None:
        resp = search_index(self.conn, "192.168.1.100")
        ip_hits = [h for h in resp.results if h.result_type == "ip"]
        assert len(ip_hits) > 0
        assert any(h.tab == "arp" for h in ip_hits)

    def test_mac_by_colon_format(self) -> None:
        # Stored as Cisco dot format; should still match colon form
        resp = search_index(self.conn, "aa:bb:cc:dd")
        assert resp.total > 0

    def test_mac_by_cisco_format(self) -> None:
        resp = search_index(self.conn, "aabb.ccdd")
        assert resp.total > 0
        mac_hits = [h for h in resp.results if h.result_type == "mac"]
        assert len(mac_hits) > 0

    def test_route_by_destination(self) -> None:
        resp = search_index(self.conn, "192.168.1.0")
        route_hits = [h for h in resp.results if h.result_type == "route"]
        assert len(route_hits) > 0
        assert any(h.tab == "routes" for h in route_hits)

    def test_route_by_next_hop(self) -> None:
        resp = search_index(self.conn, "10.0.0.254")
        assert resp.total > 0

    def test_empty_query_returns_empty(self) -> None:
        resp = search_index(self.conn, "")
        assert resp.total == 0
        assert resp.results == []

    def test_no_match(self) -> None:
        resp = search_index(self.conn, "xyzzy-no-match-12345")
        assert resp.total == 0

    def test_session_filter(self) -> None:
        # Index a second session
        result2 = _make_result("sess2")
        build_search_index(self.conn, result2)

        resp = search_index(self.conn, "core-switch", session_id="sess1")
        assert all(h.session_id == "sess1" for h in resp.results)

    def test_rebuild_replaces_old_index(self) -> None:
        """Rebuilding the index for the same session should not duplicate results."""
        build_search_index(self.conn, self.result)  # rebuild
        resp = search_index(self.conn, "core-switch-01")
        device_hits = [
            h for h in resp.results if h.result_type == "device" and h.session_id == "sess1"
        ]
        # Should only appear once, not twice
        assert len(device_hits) == 1

    def test_partial_hostname_match(self) -> None:
        resp = search_index(self.conn, "edge")
        assert any(h.device_id == "RTR1" for h in resp.results)

    def test_result_links_to_session(self) -> None:
        resp = search_index(self.conn, "10.0.0.1")
        assert all(h.session_id == "sess1" for h in resp.results if h.device_id == "SW1")

    def test_limit_respected(self) -> None:
        resp = search_index(self.conn, "Gigabit", limit=1)
        assert len(resp.results) <= 1


# ---------------------------------------------------------------------------
# In-memory fallback search
# ---------------------------------------------------------------------------


class TestInMemorySearch:
    def setup_method(self) -> None:
        self.result = _make_result()

    def test_device_by_hostname(self) -> None:
        resp = search_in_memory([self.result], "core-switch")
        assert resp.total > 0
        assert any(h.result_type == "device" for h in resp.results)

    def test_device_by_ip(self) -> None:
        resp = search_in_memory([self.result], "10.0.0.1")
        assert resp.total > 0

    def test_mac_by_partial(self) -> None:
        resp = search_in_memory([self.result], "aabbccdd")
        assert resp.total > 0

    def test_empty_query(self) -> None:
        resp = search_in_memory([self.result], "")
        assert resp.total == 0

    def test_no_match(self) -> None:
        resp = search_in_memory([self.result], "xyzzy-nothing")
        assert resp.total == 0

    def test_session_filter(self) -> None:
        result2 = _make_result("other-session")
        resp = search_in_memory([self.result, result2], "core-switch", session_id="sess1")
        assert all(h.session_id == "sess1" for h in resp.results)


# ---------------------------------------------------------------------------
# SQLite file-based integration test
# ---------------------------------------------------------------------------


class TestSearchIntegration:
    def setup_method(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.db"
        # Open the same DB that the SQLite store would open
        from backend.store_sqlite import _open_db

        self.conn = _open_db(self._db_path)

    def test_round_trip_via_store_open(self) -> None:
        result = _make_result("int-test")
        build_search_index(self.conn, result)
        resp = search_index(self.conn, "core-switch-01")
        assert resp.total > 0
        assert any(h.session_id == "int-test" for h in resp.results)
