"""NetScope — L3 path trace engine.

Phase 1: Layer-3 path tracing using routing tables only.
  - Resolves device lookup by management IP or hostname.
  - Performs longest-prefix-match on each hop's routing table.
  - Follows next-hop IPs through the topology.
  - Detects loops and dead ends with clear error reporting.

Phase 2 (future): L2 resolution using ARP + MAC tables within broadcast domains.
Phase 3 (future): VRF-aware tracing.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import TYPE_CHECKING

from backend.models import PathHop, PathTraceRequest, PathTraceResult, TopologyResult

if TYPE_CHECKING:
    from backend.models import Device, RouteEntry

logger = logging.getLogger(__name__)

MAX_HOPS = 30  # guard against routing loops we can't detect via visited set


# ---------------------------------------------------------------------------
# IP helpers
# ---------------------------------------------------------------------------


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _prefix_len(cidr: str) -> int:
    """Return prefix length for a route destination CIDR, or -1 on error."""
    try:
        return ipaddress.ip_network(cidr, strict=False).prefixlen
    except ValueError:
        return -1


def _ip_in_network(ip: str, cidr: str) -> bool:
    """Return True if *ip* is contained in *cidr* (e.g. '10.0.1.5' in '10.0.1.0/24')."""
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Topology index builders
# ---------------------------------------------------------------------------


def _build_ip_index(devices: list[Device]) -> dict[str, str]:
    """Return a map of IP → device_id for every known IP on every device.

    Covers:
    - device.mgmt_ip
    - interface.ip_address (strips prefix/mask if present)
    - arp_table entries that are self (static type)
    """
    idx: dict[str, str] = {}
    for dev in devices:
        idx[dev.mgmt_ip] = dev.id
        for intf in dev.interfaces:
            if intf.ip_address:
                raw = intf.ip_address.split("/")[0]
                idx[raw] = dev.id
    return idx


def _build_hostname_index(devices: list[Device]) -> dict[str, str]:
    """Return hostname (lower-cased) → device_id."""
    return {(dev.hostname or dev.id).lower(): dev.id for dev in devices if dev.hostname or dev.id}


def _resolve_device(identifier: str, devices: list[Device]) -> Device | None:
    """Find a Device by IP address or hostname (case-insensitive)."""
    ident_lower = identifier.lower()
    for dev in devices:
        if dev.mgmt_ip == identifier:
            return dev
        if (dev.hostname or "").lower() == ident_lower:
            return dev
        # Also check interface IPs
        for intf in dev.interfaces:
            if intf.ip_address and intf.ip_address.split("/")[0] == identifier:
                return dev
    return None


# ---------------------------------------------------------------------------
# Routing table helpers
# ---------------------------------------------------------------------------


def _longest_prefix_match(route_table: list[RouteEntry], dest_ip: str) -> RouteEntry | None:
    """Return the best matching route for *dest_ip* (longest prefix wins).

    Skips routes with malformed destination CIDRs.
    """
    best: RouteEntry | None = None
    best_len = -1
    for route in route_table:
        if not route.destination:
            continue
        plen = _prefix_len(route.destination)
        if plen < 0:
            continue
        if _ip_in_network(dest_ip, route.destination) and plen > best_len:
            best = route
            best_len = plen
    return best


def _is_local_route(route: RouteEntry) -> bool:
    """True when the route means the destination is directly reachable on this device."""
    rt = (route.route_type or "").lower()
    proto = (route.protocol or "").upper()
    return rt in ("connected", "local") or proto in ("C", "L")


# ---------------------------------------------------------------------------
# Main trace function
# ---------------------------------------------------------------------------


def trace_path(session: TopologyResult, req: PathTraceRequest) -> PathTraceResult:
    """Trace the L3 path from *source* to *dest* within *session*.

    Returns a PathTraceResult with the hop list and any break details.
    """
    devices_by_id: dict[str, Device] = {d.id: d for d in session.devices}
    ip_index = _build_ip_index(session.devices)

    source_dev = _resolve_device(req.source, session.devices)
    dest_dev = _resolve_device(req.dest, session.devices)

    # Determine the destination IP we're routing toward.
    # If dest is a hostname (not an IP), use the device's mgmt_ip.
    dest_ip = req.dest if _is_ip(req.dest) else (dest_dev.mgmt_ip if dest_dev else req.dest)

    if source_dev is None:
        return PathTraceResult(
            session_id=session.session_id,
            source=req.source,
            dest=req.dest,
            success=False,
            error=f"Source '{req.source}' not found in topology",
            break_reason="device_not_discovered",
        )

    if not _is_ip(dest_ip):
        return PathTraceResult(
            session_id=session.session_id,
            source=req.source,
            dest=req.dest,
            success=False,
            error=f"Destination '{req.dest}' not found in topology and is not an IP address",
            break_reason="device_not_discovered",
        )

    hops: list[PathHop] = []
    node_ids: list[str] = []
    link_keys: list[str] = []
    visited: set[str] = set()

    current = source_dev
    prev_id: str | None = None
    hop_num = 1

    while True:
        if current.id in visited:
            # Loop detected — we've been here before
            return PathTraceResult(
                session_id=session.session_id,
                source=req.source,
                dest=req.dest,
                success=False,
                hops=hops,
                node_ids=node_ids,
                link_keys=link_keys,
                error=f"Routing loop detected at {current.hostname or current.id}",
                break_reason="loop",
            )

        if hop_num > MAX_HOPS:
            return PathTraceResult(
                session_id=session.session_id,
                source=req.source,
                dest=req.dest,
                success=False,
                hops=hops,
                node_ids=node_ids,
                link_keys=link_keys,
                error=f"Exceeded maximum hop count ({MAX_HOPS})",
                break_reason="max_hops",
            )

        visited.add(current.id)

        # Check if the destination IP is local to this device (connected or local route)
        best_route = _longest_prefix_match(current.route_table, dest_ip)

        # Are we at the actual destination device?
        at_dest = current.id == (dest_dev.id if dest_dev else None) or current.mgmt_ip == dest_ip

        if at_dest:
            hop = PathHop(
                hop_number=hop_num,
                device_id=current.id,
                hostname=current.hostname,
                mgmt_ip=current.mgmt_ip,
            )
            hops.append(hop)
            node_ids.append(current.id)
            if prev_id:
                link_keys.append(f"{prev_id}:{current.id}")
            return PathTraceResult(
                session_id=session.session_id,
                source=req.source,
                dest=req.dest,
                success=True,
                hops=hops,
                node_ids=node_ids,
                link_keys=link_keys,
            )

        if best_route is not None and _is_local_route(best_route):
            # Destination is on a directly connected subnet of this device.
            # Record this device as the penultimate hop, then jump to dest_dev if known
            # (Phase 1 shortcut that simulates L2/ARP resolution).
            hop = PathHop(
                hop_number=hop_num,
                device_id=current.id,
                hostname=current.hostname,
                mgmt_ip=current.mgmt_ip,
                out_interface=best_route.interface,
            )
            hops.append(hop)
            node_ids.append(current.id)
            if prev_id:
                link_keys.append(f"{prev_id}:{current.id}")

            if dest_dev is not None and current.id != dest_dev.id:
                # Append the actual destination device as the final hop
                final_hop = PathHop(
                    hop_number=hop_num + 1,
                    device_id=dest_dev.id,
                    hostname=dest_dev.hostname,
                    mgmt_ip=dest_dev.mgmt_ip,
                )
                hops.append(final_hop)
                node_ids.append(dest_dev.id)
                link_keys.append(f"{current.id}:{dest_dev.id}")

            return PathTraceResult(
                session_id=session.session_id,
                source=req.source,
                dest=req.dest,
                success=True,
                hops=hops,
                node_ids=node_ids,
                link_keys=link_keys,
            )

        if best_route is None:
            hop = PathHop(
                hop_number=hop_num,
                device_id=current.id,
                hostname=current.hostname,
                mgmt_ip=current.mgmt_ip,
            )
            hops.append(hop)
            node_ids.append(current.id)
            if prev_id:
                link_keys.append(f"{prev_id}:{current.id}")
            return PathTraceResult(
                session_id=session.session_id,
                source=req.source,
                dest=req.dest,
                success=False,
                hops=hops,
                node_ids=node_ids,
                link_keys=link_keys,
                error=(
                    f"No route to {dest_ip} on {current.hostname or current.id} "
                    f"(no matching route in routing table)"
                ),
                break_reason="no_route",
            )

        next_hop_ip = best_route.next_hop
        out_intf = best_route.interface

        hop = PathHop(
            hop_number=hop_num,
            device_id=current.id,
            hostname=current.hostname,
            mgmt_ip=current.mgmt_ip,
            out_interface=out_intf,
            next_hop_ip=next_hop_ip,
        )
        hops.append(hop)
        node_ids.append(current.id)
        if prev_id:
            link_keys.append(f"{prev_id}:{current.id}")

        if not next_hop_ip:
            # Route exists but no next hop and not connected — shouldn't happen normally
            return PathTraceResult(
                session_id=session.session_id,
                source=req.source,
                dest=req.dest,
                success=False,
                hops=hops,
                node_ids=node_ids,
                link_keys=link_keys,
                error=(
                    f"Route {best_route.destination} on {current.hostname or current.id} "
                    f"has no next-hop IP and is not a connected route"
                ),
                break_reason="no_route",
            )

        # Resolve next-hop device
        next_id = ip_index.get(next_hop_ip)
        if not next_id:
            # Next-hop IP isn't on any discovered device — path exits topology
            return PathTraceResult(
                session_id=session.session_id,
                source=req.source,
                dest=req.dest,
                success=False,
                hops=hops,
                node_ids=node_ids,
                link_keys=link_keys,
                error=(
                    f"Next-hop {next_hop_ip} via {current.hostname or current.id} "
                    f"is not a discovered device — path exits known topology"
                ),
                break_reason="device_not_discovered",
            )

        next_dev = devices_by_id.get(next_id)
        if not next_dev:
            return PathTraceResult(
                session_id=session.session_id,
                source=req.source,
                dest=req.dest,
                success=False,
                hops=hops,
                node_ids=node_ids,
                link_keys=link_keys,
                error=f"Internal error: device {next_id} in IP index but not in devices list",
                break_reason="device_not_discovered",
            )

        prev_id = current.id
        current = next_dev
        hop_num += 1
