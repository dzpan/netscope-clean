"""Unit tests for the L3 path trace engine."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.models import (
    Device,
    DeviceStatus,
    InterfaceInfo,
    Link,
    PathTraceRequest,
    RouteEntry,
    TopologyResult,
)
from backend.path_trace import (
    _ip_in_network,
    _is_ip,
    _longest_prefix_match,
    _prefix_len,
    trace_path,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _dev(
    id_: str,
    mgmt_ip: str,
    routes: list[RouteEntry] | None = None,
    interfaces: list[InterfaceInfo] | None = None,
    hostname: str | None = None,
) -> Device:
    return Device(
        id=id_,
        hostname=hostname or id_,
        mgmt_ip=mgmt_ip,
        status=DeviceStatus.OK,
        route_table=routes or [],
        interfaces=interfaces or [],
    )


def _route(
    destination: str,
    next_hop: str | None = None,
    interface: str | None = None,
    route_type: str = "static",
    protocol: str = "S",
) -> RouteEntry:
    return RouteEntry(
        destination=destination,
        next_hop=next_hop,
        interface=interface,
        route_type=route_type,
        protocol=protocol,
    )


def _connected(destination: str, interface: str = "Vlan1") -> RouteEntry:
    return RouteEntry(
        destination=destination,
        next_hop=None,
        interface=interface,
        route_type="connected",
        protocol="C",
    )


def _session(*devices: Device, links: list[Link] | None = None) -> TopologyResult:
    return TopologyResult(
        session_id="test-session",
        discovered_at=datetime.now(UTC),
        devices=list(devices),
        links=links or [],
        failures=[],
    )


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


class TestIpHelpers:
    def test_is_ip_valid(self):
        assert _is_ip("10.0.0.1")
        assert _is_ip("192.168.1.100")

    def test_is_ip_invalid(self):
        assert not _is_ip("CORE-SW-01")
        assert not _is_ip("hostname.local")
        assert not _is_ip("")

    def test_ip_in_network(self):
        assert _ip_in_network("10.0.0.5", "10.0.0.0/24")
        assert _ip_in_network("10.0.0.1", "10.0.0.0/8")
        assert not _ip_in_network("10.0.1.5", "10.0.0.0/24")

    def test_prefix_len(self):
        assert _prefix_len("10.0.0.0/24") == 24
        assert _prefix_len("0.0.0.0/0") == 0
        assert _prefix_len("bad") == -1

    def test_longest_prefix_match_prefers_more_specific(self):
        routes = [
            _route("0.0.0.0/0", next_hop="10.0.0.254"),
            _route("10.0.1.0/24", next_hop="10.0.0.2"),
        ]
        match = _longest_prefix_match(routes, "10.0.1.5")
        assert match is not None
        assert match.destination == "10.0.1.0/24"

    def test_longest_prefix_match_default_route(self):
        routes = [_route("0.0.0.0/0", next_hop="10.0.0.254")]
        match = _longest_prefix_match(routes, "8.8.8.8")
        assert match is not None
        assert match.destination == "0.0.0.0/0"

    def test_longest_prefix_match_no_route(self):
        routes = [_route("10.0.0.0/24", next_hop="10.0.1.1")]
        match = _longest_prefix_match(routes, "192.168.1.1")
        assert match is None


# ---------------------------------------------------------------------------
# Trace path tests
# ---------------------------------------------------------------------------


class TestTracePath:
    def test_source_not_found(self):
        d1 = _dev("SW1", "10.0.0.1")
        sess = _session(d1)
        req = PathTraceRequest(source="192.168.99.99", dest="10.0.0.1")
        result = trace_path(sess, req)
        assert not result.success
        assert result.break_reason == "device_not_discovered"

    def test_source_is_dest(self):
        """Single device, source == dest → trivially at destination."""
        d1 = _dev(
            "SW1",
            "10.0.0.1",
            routes=[_connected("10.0.0.0/24", "Vlan1")],
        )
        sess = _session(d1)
        req = PathTraceRequest(source="10.0.0.1", dest="10.0.0.1")
        result = trace_path(sess, req)
        assert result.success
        assert len(result.hops) == 1
        assert result.hops[0].device_id == "SW1"

    def test_direct_connected_route(self):
        """Dest IP is on a connected subnet of the source device."""
        d1 = _dev(
            "SW1",
            "10.0.0.1",
            routes=[_connected("10.0.0.0/24", "Vlan1")],
        )
        sess = _session(d1)
        req = PathTraceRequest(source="10.0.0.1", dest="10.0.0.5")
        result = trace_path(sess, req)
        assert result.success
        assert len(result.hops) == 1
        assert result.node_ids == ["SW1"]

    def test_two_hop_path(self):
        """SW1 → SW2, where SW2 has a connected route to dest subnet."""
        sw1 = _dev(
            "SW1",
            "10.0.0.1",
            routes=[
                _connected("10.0.0.0/24", "Vlan1"),
                _route("10.0.1.0/24", next_hop="10.0.0.2", route_type="ospf", protocol="O"),
            ],
        )
        sw2 = _dev(
            "SW2",
            "10.0.0.2",
            routes=[
                _connected("10.0.0.0/24", "Vlan1"),
                _connected("10.0.1.0/24", "Vlan10"),
            ],
        )
        sess = _session(sw1, sw2)
        req = PathTraceRequest(source="10.0.0.1", dest="10.0.1.50")
        result = trace_path(sess, req)
        assert result.success
        assert len(result.hops) == 2
        assert result.hops[0].device_id == "SW1"
        assert result.hops[1].device_id == "SW2"
        assert "SW1" in result.node_ids
        assert "SW2" in result.node_ids

    def test_three_hop_path(self):
        """SW1 → SW2 → SW3 where SW3 is the destination."""
        sw1 = _dev(
            "SW1",
            "10.0.0.1",
            routes=[
                _connected("10.0.0.0/24"),
                _route("10.0.2.0/24", next_hop="10.0.0.2"),
            ],
        )
        sw2 = _dev(
            "SW2",
            "10.0.0.2",
            routes=[
                _connected("10.0.0.0/24"),
                _route("10.0.2.0/24", next_hop="10.0.1.3"),
            ],
            interfaces=[InterfaceInfo(name="Vlan20", ip_address="10.0.1.2")],
        )
        sw3 = _dev(
            "SW3",
            "10.0.1.3",
            routes=[
                _connected("10.0.1.0/24"),
                _connected("10.0.2.0/24"),
            ],
        )
        sess = _session(sw1, sw2, sw3)
        req = PathTraceRequest(source="10.0.0.1", dest="10.0.2.5")
        result = trace_path(sess, req)
        assert result.success
        assert len(result.hops) == 3
        assert [h.device_id for h in result.hops] == ["SW1", "SW2", "SW3"]

    def test_no_route(self):
        """No route to dest → break_reason=no_route."""
        d1 = _dev("SW1", "10.0.0.1", routes=[_connected("10.0.0.0/24")])
        sess = _session(d1)
        req = PathTraceRequest(source="10.0.0.1", dest="172.16.0.1")
        result = trace_path(sess, req)
        assert not result.success
        assert result.break_reason == "no_route"
        assert len(result.hops) == 1  # recorded the hop before the break

    def test_next_hop_not_discovered(self):
        """Next-hop IP exists in route table but device isn't discovered."""
        d1 = _dev(
            "SW1",
            "10.0.0.1",
            routes=[_route("172.16.0.0/24", next_hop="10.0.0.99")],
        )
        sess = _session(d1)
        req = PathTraceRequest(source="10.0.0.1", dest="172.16.0.1")
        result = trace_path(sess, req)
        assert not result.success
        assert result.break_reason == "device_not_discovered"
        assert result.hops[0].device_id == "SW1"

    def test_loop_detection(self):
        """Routing loop: SW1 → SW2 → SW1 → …"""
        sw1 = _dev(
            "SW1",
            "10.0.0.1",
            routes=[_route("10.0.2.0/24", next_hop="10.0.0.2")],
        )
        sw2 = _dev(
            "SW2",
            "10.0.0.2",
            routes=[_route("10.0.2.0/24", next_hop="10.0.0.1")],  # points back to SW1
        )
        sess = _session(sw1, sw2)
        req = PathTraceRequest(source="10.0.0.1", dest="10.0.2.1")
        result = trace_path(sess, req)
        assert not result.success
        assert result.break_reason == "loop"

    def test_lookup_by_hostname(self):
        """Source specified as hostname, not IP."""
        sw1 = _dev("SW1", "10.0.0.1", hostname="CORE-SW-01")
        sw1.route_table = [_connected("10.0.0.0/24")]
        sess = _session(sw1)
        req = PathTraceRequest(source="CORE-SW-01", dest="10.0.0.5")
        result = trace_path(sess, req)
        assert result.success
        assert result.hops[0].device_id == "SW1"

    def test_dest_by_hostname(self):
        """Destination specified as hostname → resolved to mgmt_ip for routing."""
        sw1 = _dev(
            "SW1",
            "10.0.0.1",
            routes=[
                _connected("10.0.0.0/24"),
                _route("10.0.1.0/24", next_hop="10.0.0.2"),
            ],
        )
        sw2 = _dev("SW2", "10.0.0.2", hostname="ACCESS-SW-02")
        sw2.route_table = [_connected("10.0.0.0/24"), _connected("10.0.1.0/24")]
        sess = _session(sw1, sw2)
        req = PathTraceRequest(source="10.0.0.1", dest="ACCESS-SW-02")
        result = trace_path(sess, req)
        assert result.success
        assert result.hops[-1].device_id == "SW2"

    def test_link_keys_populated(self):
        """link_keys contains src:tgt pairs for each traversed edge."""
        sw1 = _dev(
            "SW1",
            "10.0.0.1",
            routes=[
                _connected("10.0.0.0/24"),
                _route("10.0.1.0/24", next_hop="10.0.0.2"),
            ],
        )
        sw2 = _dev(
            "SW2",
            "10.0.0.2",
            routes=[_connected("10.0.0.0/24"), _connected("10.0.1.0/24")],
        )
        sess = _session(sw1, sw2)
        req = PathTraceRequest(source="10.0.0.1", dest="10.0.1.5")
        result = trace_path(sess, req)
        assert result.success
        # Two hops → one link key
        assert len(result.link_keys) == 1
        assert result.link_keys[0] == "SW1:SW2"
