"""Async BFS discovery engine using Scrapli."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.command_sets import groups_for_profile
from backend.models import (
    AuthType,
    CredentialSet,
    Device,
    DeviceStatus,
    DiscoverRequest,
    DiscoveryProgress,
    DiscoveryProtocol,
    Failure,
    Link,
    NativeVlanMismatch,
    NeighborRecord,
    TopologyResult,
)
from backend.normalizer import (
    build_placeholder_devices,
    collapse_port_channel_links,
    is_in_scope,
    normalize_interface_name,
    normalize_links,
    reconcile_placeholders,
)
from backend.parsers import (
    build_interface_ip_map,
    parse_arp_table,
    parse_bgp_evpn_summary,
    parse_cdp_neighbors,
    parse_etherchannel_summary,
    parse_interfaces_status,
    parse_interfaces_trunk,
    parse_inventory,
    parse_ip_interface_brief,
    parse_ip_route,
    parse_lldp_neighbors,
    parse_mac_address_table,
    parse_nve_peers,
    parse_nve_vni,
    parse_show_version,
    parse_spanning_tree,
    parse_vlan_brief,
)
from backend.utils import safe_close

logger = logging.getLogger(__name__)

try:
    from scrapli.driver.core import AsyncIOSXEDriver

    SCRAPLI_AVAILABLE = True
except ImportError:
    SCRAPLI_AVAILABLE = False
    logger.warning("Scrapli not available — discovery will not function")


async def _adaptive_on_open(conn: Any) -> None:
    """Terminal setup that works across IOS-XE, NX-OS, and CBS/C1200.

    IOS-XE and NX-OS support ``terminal length 0`` for pagination.
    CBS / C1200 Small Business switches do NOT — they need ``terminal datadump``.
    We try the standard command first and fall back if it fails or returns an error.
    """
    await conn.acquire_priv(desired_priv=conn.default_desired_privilege_level)

    # Disable pagination
    paging_ok = False
    try:
        resp = await conn.send_command("terminal length 0")
        if "%" not in resp.result:
            paging_ok = True
    except Exception:
        pass
    if not paging_ok:
        try:
            await conn.send_command("terminal datadump")
        except Exception:
            logger.debug("Neither 'terminal length 0' nor 'terminal datadump' worked")

    # Set terminal width
    try:
        await conn.send_command("terminal width 512")
    except Exception:
        try:
            await conn.send_command("terminal width 0")
        except Exception:
            pass


def _base_opts(host: str, creds: CredentialSet, timeout: int) -> dict[str, Any]:
    """Build scrapli connection options with asyncssh transport."""
    opts: dict[str, Any] = {
        "host": host,
        "auth_username": creds.username,
        "auth_password": creds.password,
        "auth_strict_key": False,
        "transport": "asyncssh",
        "timeout_socket": timeout,
        "timeout_transport": timeout,
        "timeout_ops": timeout,
        "on_open": _adaptive_on_open,
    }
    if creds.auth_type == AuthType.SSH_KEY and creds.ssh_private_key:
        opts["auth_private_key"] = creds.ssh_private_key
        if creds.ssh_key_passphrase:
            opts["auth_private_key_passphrase"] = creds.ssh_key_passphrase
        # Clear password when using key auth to avoid fallback confusion
        opts["auth_password"] = ""
    if creds.enable_password:
        opts["auth_secondary"] = creds.enable_password
    return opts


def _build_cred_list(req: DiscoverRequest) -> list[CredentialSet]:
    """Return ordered list of credentials to try. Explicit sets first, primary as fallback."""
    creds: list[CredentialSet] = list(req.credential_sets)
    if req.username:
        primary = CredentialSet(
            username=req.username,
            password=req.password,
            enable_password=req.enable_password,
        )
        already = any(
            c.username == primary.username and c.password == primary.password for c in creds
        )
        if not already:
            creds.append(primary)
    return creds


def _classify_error(exc: Exception) -> str:
    """Classify an exception into a failure reason category.

    Checks the full exception chain (__cause__ / __context__) so that
    wrapped exceptions (e.g. scrapli wrapping asyncssh) are handled.
    """
    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        messages.append(str(current).lower())
        # Walk the chain: __cause__ (explicit) then __context__ (implicit)
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)

    full = " ".join(messages)

    if any(k in full for k in ("auth", "permission", "password", "keyboard", "privilege")):
        return "auth_failed"
    if "timeout" in full or "timed out" in full:
        return "timeout"
    if any(k in full for k in ("refused", "unreachable", "no route", "no matching host")):
        return "unreachable"
    # "connection not opened" without auth keywords = genuine connectivity issue
    if "not opened" in full or "connect" in full:
        return "unreachable"
    return "unknown"


_SWITCH_PLATFORM_MARKERS = (
    "switch",
    "catalyst",
    "ws-c",
    "c93",
    "c92",
    "c91",
    "c90",
    "c38",
    "c36",
    "c35",
    "n9k",
    "n7k",
    "n5k",
    "nexus",
)

_NON_SWITCH_CAPABILITIES = frozenset({"Trans-Bridge", "Phone", "Host"})


def _is_switch_neighbor(nb: NeighborRecord) -> bool:
    """Return True if the neighbor looks like a switch/router we should BFS into.

    Uses platform string heuristics.  Filters out APs, phones, and other
    end-station devices that would bloat the topology graph.
    """
    platform = (nb.platform or "").lower()
    if any(marker in platform for marker in _SWITCH_PLATFORM_MARKERS):
        return True
    # Capability check: CDP platform field may contain capability keywords
    # e.g. "Trans-Bridge" → AP, "Phone" → IP phone
    for cap in _NON_SWITCH_CAPABILITIES:
        if cap.lower() in platform:
            return False
    # Unknown platform: default to True (include) rather than silently drop
    return True


def _detect_native_vlan_mismatches(
    devices: list[Device], links: list[Link]
) -> list[NativeVlanMismatch]:
    """Compare native VLANs on both ends of each link and return mismatches.

    For each link, looks up the trunk_info for the source_intf on the source
    device and the target_intf on the target device. If both ends have a known
    native_vlan and they differ, a NativeVlanMismatch is reported.

    Port names are normalized before lookup so that abbreviated names (e.g.
    "Gi1/0/1") and full names (e.g. "GigabitEthernet1/0/1") resolve to the
    same entry.
    """
    # Build per-device lookup: normalized_intf_name → native_vlan (trunking only)
    device_map: dict[str, Device] = {d.id: d for d in devices}

    def _native_vlan_lookup(device_id: str, intf: str) -> str | None:
        dev = device_map.get(device_id)
        if dev is None or not dev.trunk_info:
            return None
        norm_intf = normalize_interface_name(intf)
        for port, info in dev.trunk_info.items():
            if normalize_interface_name(port) == norm_intf:
                return info.native_vlan
        return None

    mismatches: list[NativeVlanMismatch] = []
    for link in links:
        src_vlan = _native_vlan_lookup(link.source, link.source_intf)
        tgt_intf = link.target_intf or ""
        tgt_vlan = _native_vlan_lookup(link.target, tgt_intf)
        if src_vlan and tgt_vlan and src_vlan != tgt_vlan:
            mismatches.append(
                NativeVlanMismatch(
                    source=link.source,
                    target=link.target,
                    source_intf=link.source_intf,
                    target_intf=tgt_intf,
                    source_native_vlan=src_vlan,
                    target_native_vlan=tgt_vlan,
                )
            )
    return mismatches


ProgressCallback = Any  # Callable[[DiscoveryProgress], None] — kept loose for mypy


async def run_discovery(
    req: DiscoverRequest,
    progress_callback: ProgressCallback | None = None,
) -> TopologyResult:
    """Entry point: perform BFS discovery and return a TopologyResult."""
    session_id = str(uuid4())
    semaphore = asyncio.Semaphore(req.max_concurrency)

    visited: set[str] = set()
    devices: dict[str, Device] = {}
    raw_links: list[Link] = []
    failures: list[Failure] = []
    all_neighbors: list[NeighborRecord] = []

    tasks: list[asyncio.Task[None]] = []
    in_progress_count = 0

    def _emit_progress(
        latest_device: str | None = None,
        latest_status: str | None = None,
        phase: str = "discovering",
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(
            DiscoveryProgress(
                session_id=session_id,
                total_queued=len(visited),
                discovered=len(devices),
                failed=len(failures),
                in_progress=in_progress_count,
                latest_device=latest_device,
                latest_status=latest_status,
                phase=phase,
            )
        )

    async def worker(ip: str, depth: int) -> None:
        nonlocal in_progress_count
        async with semaphore:
            in_progress_count += 1
            _emit_progress(latest_device=ip, latest_status="connecting", phase="discovering")

            result = await _discover_device(ip, depth, req)
            in_progress_count -= 1

            if result is None:
                _emit_progress(phase="discovering")
                return
            device, neighbors, links, failure = result

            if failure:
                failures.append(failure)
            if device:
                devices[device.id] = device
            raw_links.extend(links)
            all_neighbors.extend(neighbors)

            _emit_progress(
                latest_device=device.hostname if device else ip,
                latest_status=device.status if device else (failure.reason if failure else None),
                phase="discovering",
            )

            if depth < req.max_hops:
                for nb in neighbors:
                    target = nb.ip_address or nb.device_id
                    if not target or target in visited:
                        continue
                    if nb.ip_address and not is_in_scope(nb.ip_address, req.scope):
                        logger.debug("Skipping %s (out of scope)", nb.ip_address)
                        continue
                    if req.switch_only and not _is_switch_neighbor(nb):
                        logger.debug(
                            "Skipping %s (switch_only filter, platform=%r)",
                            nb.device_id,
                            nb.platform,
                        )
                        continue
                    logger.info(
                        "[depth=%d] Enqueuing neighbor %s → %s", depth, nb.device_id, target
                    )
                    visited.add(target)
                    tasks.append(asyncio.create_task(worker(target, depth + 1)))

    # Seed initial IPs
    for seed in req.seeds:
        visited.add(seed)
        tasks.append(asyncio.create_task(worker(seed, 0)))

    # Wave-by-wave BFS
    while tasks:
        current = list(tasks)
        tasks.clear()
        await asyncio.wait(current, return_when=asyncio.ALL_COMPLETED)

    _emit_progress(phase="finalizing")

    # --- Reconcile CDP device-IDs with discovered device-IDs ---
    # CDP may report a neighbor as "0cd5.d366.24cc" (MAC) while we discovered it
    # by IP and stored it as "AP-LOBBY" (hostname). Fix links and neighbors so
    # they reference the actual device ID, preventing phantom placeholders.
    ip_to_id = {d.mgmt_ip: d.id for d in devices.values()}
    cdp_to_real: dict[str, str] = {}
    for nb in all_neighbors:
        if nb.ip_address and nb.ip_address in ip_to_id:
            real_id = ip_to_id[nb.ip_address]
            if nb.device_id != real_id:
                cdp_to_real[nb.device_id] = real_id

    if cdp_to_real:
        logger.info(
            "Reconciling %d CDP device IDs → discovered IDs: %s", len(cdp_to_real), cdp_to_real
        )
        raw_links = [
            lk.model_copy(
                update={
                    "source": cdp_to_real.get(lk.source, lk.source),
                    "target": cdp_to_real.get(lk.target, lk.target),
                }
            )
            for lk in raw_links
        ]
        all_neighbors = [
            NeighborRecord(
                device_id=cdp_to_real.get(nb.device_id, nb.device_id),
                ip_address=nb.ip_address,
                local_interface=nb.local_interface,
                remote_interface=nb.remote_interface,
                platform=nb.platform,
                protocol=nb.protocol,
            )
            for nb in all_neighbors
        ]

    # Placeholder devices for neighbors that were never reachable
    placeholders = build_placeholder_devices(all_neighbors, set(devices.keys()))
    for p in placeholders:
        if p.id not in devices:
            devices[p.id] = p

    # Final reconciliation: replace placeholders whose IP matches a real device
    final_devices, final_links = reconcile_placeholders(
        list(devices.values()), normalize_links(raw_links)
    )

    # Backfill platform from CDP/LLDP neighbor data for devices that were
    # discovered OK but whose show version / show inventory had no platform
    # (common for CBS/C1200 switches).
    _backfill_platform_from_neighbors(final_devices, all_neighbors)

    # Collapse port-channel member links into single labeled edges
    final_links = collapse_port_channel_links(final_links, final_devices)

    # Native VLAN mismatch detection — compare both ends of each link
    native_vlan_mismatches = _detect_native_vlan_mismatches(final_devices, final_links)

    _emit_progress(phase="done")

    return TopologyResult(
        session_id=session_id,
        discovered_at=datetime.now(UTC),
        devices=final_devices,
        links=final_links,
        failures=failures,
        native_vlan_mismatches=native_vlan_mismatches,
    )


def _backfill_platform_from_neighbors(
    devices: list[Device],
    neighbors: list[NeighborRecord],
) -> None:
    """Backfill missing platform fields from CDP/LLDP neighbor reports.

    CBS/C1200 switches often have no platform in ``show version`` or
    ``show inventory``.  Other switches that see them via CDP will report
    their platform (e.g. ``cisco C1200-8T-E-2G``).  Use that data to fill
    in the gap — mutates *devices* in place.
    """
    # Build device_id → platform from neighbor reports
    neighbor_platform: dict[str, str] = {}
    for nb in neighbors:
        if nb.platform and nb.device_id not in neighbor_platform:
            neighbor_platform[nb.device_id] = nb.platform

    for dev in devices:
        if dev.platform:
            continue
        cdp_platform = neighbor_platform.get(dev.id) or neighbor_platform.get(dev.hostname or "")
        if cdp_platform:
            dev.platform = cdp_platform
            logger.debug(
                "Backfilled platform for %s from neighbor data: %s",
                dev.id,
                cdp_platform,
            )


def _merge_neighbors(
    cdp: list[NeighborRecord],
    lldp: list[NeighborRecord],
) -> list[NeighborRecord]:
    """Merge CDP and LLDP neighbor lists, deduplicating on (local_interface, remote_ip).

    When both protocols report the same neighbor on the same local port,
    keep the one with richer metadata (prefer System Name over Chassis ID).
    """
    merged: dict[tuple[str, str | None], NeighborRecord] = {}

    # Index CDP neighbors first
    for n in cdp:
        key = (n.local_interface, n.ip_address)
        merged[key] = n

    # Overlay LLDP — replace CDP entry only if LLDP has richer data
    for n in lldp:
        key = (n.local_interface, n.ip_address)
        existing = merged.get(key)
        if existing is None:
            merged[key] = n
        else:
            # LLDP with System Name is richer than CDP with just device_id
            # Also prefer LLDP if it has capabilities or more fields populated
            lldp_richness = sum(
                [
                    bool(n.capabilities),
                    bool(n.chassis_id_subtype),
                    bool(n.port_description),
                    bool(n.platform),
                ]
            )
            cdp_richness = sum(
                [
                    bool(existing.platform),
                    bool(existing.remote_interface),
                ]
            )
            if lldp_richness >= cdp_richness:
                merged[key] = n

    return list(merged.values())


async def _discover_device(
    ip: str,
    depth: int,
    req: DiscoverRequest,
) -> tuple[Device | None, list[NeighborRecord], list[Link], Failure | None] | None:
    """Connect to a single device, trying each credential set in order.

    Uses explicit open/close instead of ``async with`` to prevent scrapli's
    ``__aexit__`` from swallowing authentication exceptions when closing a
    failed connection.
    """
    if not SCRAPLI_AVAILABLE:
        return None

    cred_list = _build_cred_list(req)
    if not cred_list:
        return None, [], [], Failure(target=ip, reason="unknown", detail="No credentials provided")

    last_exc: Exception | None = None

    for i, creds in enumerate(cred_list, 1):
        opts = _base_opts(ip, creds, req.timeout)
        conn = AsyncIOSXEDriver(**opts)

        # --- Phase 1: open connection ---
        try:
            await conn.open()
        except Exception as exc:
            await safe_close(conn)
            last_exc = exc
            reason = _classify_error(exc)
            if reason != "auth_failed":
                logger.info(
                    "[depth=%d] %s → %s (%s), not retrying credentials", depth, ip, reason, exc
                )
                break
            logger.info(
                "[depth=%d] %s → auth failed with creds %d/%d ('%s')",
                depth,
                ip,
                i,
                len(cred_list),
                creds.username,
            )
            continue

        # --- Phase 2: run commands (connection is open) ---
        try:
            ver_resp = await conn.send_command("show version")
            version = parse_show_version(ver_resp.result)

            # Platform fallback: CBS/C1200 show version lacks platform info.
            # Try "show inventory" and use the first Chassis PID.
            if not version.platform:
                try:
                    inv_resp = await conn.send_command("show inventory")
                    inv_items = parse_inventory(inv_resp.result)
                    if inv_items:
                        # Prefer the Chassis entry; fall back to first item with a PID
                        chassis = next(
                            (i for i in inv_items if "chassis" in (i.name or "").lower()),
                            None,
                        )
                        pid_item = chassis or next((i for i in inv_items if i.pid), None)
                        if pid_item and pid_item.pid:
                            version = version.model_copy(update={"platform": pid_item.pid})
                except Exception:
                    pass

            # Hostname: prefer show-version, fall back to CLI prompt
            hostname = version.hostname
            if not hostname:
                try:
                    prompt = await conn.get_prompt()
                    hostname = prompt.rstrip("#>() ").split("(")[0].strip() or None
                except Exception:
                    pass
            hostname = hostname or ip
            device_id = hostname

            neighbors: list[NeighborRecord] = []
            proto = req.discovery_protocol
            protocol_used = "CDP" if proto == DiscoveryProtocol.CDP_PREFER else "LLDP"

            if proto == DiscoveryProtocol.BOTH:
                # Run both protocols and merge results
                cdp_neighbors: list[NeighborRecord] = []
                lldp_neighbors: list[NeighborRecord] = []
                try:
                    cdp_resp = await conn.send_command("show cdp neighbors detail")
                    if cdp_resp.result and "CDP is not enabled" not in cdp_resp.result:
                        cdp_neighbors = parse_cdp_neighbors(cdp_resp.result)
                except Exception:
                    pass
                try:
                    lldp_resp = await conn.send_command("show lldp neighbors detail")
                    if lldp_resp.result and "LLDP is not enabled" not in lldp_resp.result:
                        lldp_neighbors = parse_lldp_neighbors(lldp_resp.result)
                except Exception:
                    pass
                neighbors = _merge_neighbors(cdp_neighbors, lldp_neighbors)
                protocol_used = "CDP+LLDP"
                if not neighbors:
                    logger.debug("[%s] Both CDP and LLDP returned 0 neighbors", ip)
            elif proto == DiscoveryProtocol.CDP_PREFER:
                cdp_resp = await conn.send_command("show cdp neighbors detail")
                if cdp_resp.result and "CDP is not enabled" not in cdp_resp.result:
                    neighbors = parse_cdp_neighbors(cdp_resp.result)
                    if not neighbors:
                        logger.debug(
                            "[%s] CDP returned 0 neighbors, raw length=%d",
                            ip,
                            len(cdp_resp.result),
                        )
                if not neighbors:
                    # Fallback to LLDP if CDP found nothing
                    try:
                        lldp_resp = await conn.send_command("show lldp neighbors detail")
                        if lldp_resp.result and "LLDP is not enabled" not in lldp_resp.result:
                            neighbors = parse_lldp_neighbors(lldp_resp.result)
                            if neighbors:
                                protocol_used = "LLDP"
                            else:
                                logger.debug("[%s] LLDP also returned 0 neighbors", ip)
                    except Exception:
                        pass
            else:
                # LLDP_PREFER
                lldp_resp = await conn.send_command("show lldp neighbors detail")
                if lldp_resp.result and "LLDP is not enabled" not in lldp_resp.result:
                    neighbors = parse_lldp_neighbors(lldp_resp.result)
                    if not neighbors:
                        logger.debug("[%s] LLDP returned output but parsed 0 neighbors", ip)
                if not neighbors:
                    # Fallback to CDP if LLDP found nothing
                    try:
                        cdp_resp = await conn.send_command("show cdp neighbors detail")
                        if cdp_resp.result and "CDP is not enabled" not in cdp_resp.result:
                            neighbors = parse_cdp_neighbors(cdp_resp.result)
                            if neighbors:
                                protocol_used = "CDP"
                    except Exception:
                        pass

            # Determine which data groups to collect based on the profile
            active_groups = groups_for_profile(req.collection_profile, req.custom_groups)

            # Interfaces
            interfaces = []
            if "interfaces" in active_groups:
                try:
                    intf_resp = await conn.send_command("show interfaces status")
                    interfaces = parse_interfaces_status(intf_resp.result)
                except Exception:
                    pass
                if not interfaces:
                    try:
                        intf_resp = await conn.send_command("show ip interface brief")
                        interfaces = parse_ip_interface_brief(intf_resp.result)
                    except Exception:
                        pass

                # Merge IP addresses from show ip interface brief
                try:
                    ip_brief_resp = await conn.send_command("show ip interface brief")
                    ip_map = build_interface_ip_map(ip_brief_resp.result)
                    if ip_map:
                        for intf in interfaces:
                            intf_ip = ip_map.get(intf.name)
                            if intf_ip:
                                intf.ip_address = intf_ip
                except Exception:
                    pass

            # VLANs — try IOS-XE command first, fall back to CBS/C1200 command
            vlans = []
            if "vlans" in active_groups:
                try:
                    vlan_resp = await conn.send_command("show vlan brief")
                    vlans = parse_vlan_brief(vlan_resp.result)
                except Exception:
                    pass
                if not vlans:
                    try:
                        vlan_resp = await conn.send_command("show vlan")
                        vlans = parse_vlan_brief(vlan_resp.result)
                    except Exception:
                        pass

            # ARP table — try IOS-XE command first, fall back to CBS/C1200 command
            arp_table = []
            if "arp" in active_groups:
                try:
                    arp_resp = await conn.send_command("show ip arp")
                    arp_table = parse_arp_table(arp_resp.result)
                except Exception:
                    pass
                if not arp_table:
                    try:
                        arp_resp = await conn.send_command("show arp")
                        arp_table = parse_arp_table(arp_resp.result)
                    except Exception:
                        pass

            # MAC address table
            mac_table = []
            if "mac" in active_groups:
                try:
                    mac_resp = await conn.send_command("show mac address-table")
                    mac_table = parse_mac_address_table(mac_resp.result)
                except Exception:
                    pass

            # Routing table
            route_table = []
            if "routes" in active_groups:
                try:
                    route_resp = await conn.send_command("show ip route")
                    route_table = parse_ip_route(route_resp.result)
                except Exception:
                    pass

            # EtherChannel summary
            etherchannels = []
            if "etherchannel" in active_groups:
                try:
                    ec_resp = await conn.send_command("show etherchannel summary")
                    etherchannels = parse_etherchannel_summary(ec_resp.result)
                except Exception:
                    pass

            # Spanning Tree
            stp_info = []
            if "spanning_tree" in active_groups:
                try:
                    stp_resp = await conn.send_command("show spanning-tree")
                    stp_info = parse_spanning_tree(stp_resp.result)
                except Exception:
                    pass

            # Trunk interfaces
            trunk_info = {}
            if "trunks" in active_groups:
                try:
                    trunk_resp = await conn.send_command("show interfaces trunk")
                    trunk_info = parse_interfaces_trunk(trunk_resp.result)
                except Exception:
                    pass

            # NVE peers (VXLAN)
            nve_peers = []
            if "vxlan" in active_groups:
                try:
                    nve_resp = await conn.send_command("show nve peers")
                    nve_peers = parse_nve_peers(nve_resp.result)
                except Exception:
                    pass

            # NVE VNI mappings (VXLAN)
            vni_mappings = []
            if "vxlan" in active_groups:
                try:
                    vni_resp = await conn.send_command("show nve vni")
                    vni_mappings = parse_nve_vni(vni_resp.result)
                except Exception:
                    pass

            # BGP EVPN summary (VXLAN)
            evpn_neighbors = []
            if "vxlan" in active_groups:
                try:
                    evpn_resp = await conn.send_command("show bgp l2vpn evpn summary")
                    evpn_neighbors = parse_bgp_evpn_summary(evpn_resp.result)
                except Exception:
                    pass

            await safe_close(conn)

            device = Device(
                id=device_id,
                hostname=hostname,
                mgmt_ip=ip,
                platform=version.platform,
                serial=version.serial,
                os_version=version.os_version,
                uptime=version.uptime,
                status=DeviceStatus.OK,
                interfaces=interfaces,
                vlans=vlans,
                arp_table=arp_table,
                mac_table=mac_table,
                route_table=route_table,
                etherchannels=etherchannels,
                stp_info=stp_info,
                trunk_info=trunk_info,
                nve_peers=nve_peers,
                vni_mappings=vni_mappings,
                evpn_neighbors=evpn_neighbors,
                base_mac=version.base_mac,
            )

            links = [
                Link(
                    source=device_id,
                    target=nb.device_id,
                    source_intf=nb.local_interface,
                    target_intf=nb.remote_interface,
                    protocol=nb.protocol,
                    capabilities=nb.capabilities,
                    system_description=nb.platform,
                    chassis_id_subtype=nb.chassis_id_subtype,
                    port_id_subtype=nb.port_id_subtype,
                    port_description=nb.port_description,
                    med_device_type=nb.med_device_type,
                    med_poe_requested=nb.med_poe_requested,
                    med_poe_allocated=nb.med_poe_allocated,
                    med_network_policy=nb.med_network_policy,
                )
                for nb in neighbors
            ]

            no_neighbor_failure = (
                None
                if neighbors
                else Failure(
                    target=ip,
                    reason="no_cdp_lldp",
                    detail=f"No {protocol_used} neighbors found on {hostname}",
                )
            )

            logger.info(
                "[depth=%d] %s → OK (%s, creds: %s, profile: %s)  "
                "neighbors=%d  intfs=%d  vlans=%d  arp=%d  mac=%d  "
                "routes=%d  ec=%d  stp=%d  trunks=%d  nve=%d  vni=%d  evpn=%d",
                depth,
                ip,
                hostname,
                creds.username,
                req.collection_profile.value,
                len(neighbors),
                len(interfaces),
                len(vlans),
                len(arp_table),
                len(mac_table),
                len(route_table),
                len(etherchannels),
                len(stp_info),
                len(trunk_info),
                len(nve_peers),
                len(vni_mappings),
                len(evpn_neighbors),
            )
            return device, neighbors, links, no_neighbor_failure

        except Exception as exc:
            await safe_close(conn)
            last_exc = exc
            reason = _classify_error(exc)
            if reason != "auth_failed":
                break
            logger.info(
                "[depth=%d] %s → auth failed during commands with creds %d/%d",
                depth,
                ip,
                i,
                len(cred_list),
            )
            continue

    # All credential sets exhausted or non-auth failure
    reason = _classify_error(last_exc) if last_exc else "unknown"
    logger.warning("[depth=%d] %s → %s: %s", depth, ip, reason, last_exc)
    return None, [], [], Failure(target=ip, reason=reason, detail=str(last_exc))


async def probe_device(
    host: str,
    username: str,
    password: str,
    enable_password: str | None,
    timeout: int,
) -> tuple[bool, dict[str, str | None]]:
    """Quick connectivity and credential test — runs show version only."""
    if not SCRAPLI_AVAILABLE:
        return False, {"error": "Scrapli not installed"}

    creds = CredentialSet(username=username, password=password, enable_password=enable_password)
    opts = _base_opts(host, creds, timeout)
    conn = AsyncIOSXEDriver(**opts)
    try:
        await conn.open()
        resp = await conn.send_command("show version")
        ver = parse_show_version(resp.result)
        await safe_close(conn)
        return True, {
            "hostname": ver.hostname,
            "platform": ver.platform,
            "os_version": ver.os_version,
        }
    except Exception as exc:
        await safe_close(conn)
        return False, {"error": str(exc)}
