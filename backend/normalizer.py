"""Link deduplication and placeholder device creation."""

from __future__ import annotations

import ipaddress
import re
from collections import defaultdict
from typing import TypedDict

from backend.models import (
    Device,
    DeviceStatus,
    EtherChannelInfo,
    Link,
    LinkMember,
    NeighborRecord,
    VlanMapEntry,
)


class _VlanBucket(TypedDict):
    name: str | None
    devices: set[str]
    trunk_ports: int
    access_ports: int


def normalize_links(raw_links: list[Link]) -> list[Link]:
    """Deduplicate bidirectional links, keeping the first occurrence.

    Interface names are normalized before building the dedup key so that
    abbreviated names (e.g. ``Gi1/0/1``) and full names (e.g.
    ``GigabitEthernet1/0/1``) are treated as the same endpoint.
    """
    seen: set[frozenset[str]] = set()
    result: list[Link] = []
    for link in raw_links:
        src_norm = normalize_interface_name(link.source_intf)
        tgt_norm = normalize_interface_name(link.target_intf or "")
        key = frozenset({f"{link.source}:{src_norm}", f"{link.target}:{tgt_norm}"})
        if key not in seen:
            seen.add(key)
            result.append(link)
    return result


def build_placeholder_devices(
    neighbors: list[NeighborRecord],
    discovered_ids: set[str],
) -> list[Device]:
    """Create placeholder Device entries for neighbors that were not discovered."""
    placeholders: list[Device] = []
    seen_ids: set[str] = set()

    for nb in neighbors:
        dev_id = nb.device_id
        if dev_id in discovered_ids or dev_id in seen_ids:
            continue
        seen_ids.add(dev_id)
        placeholders.append(
            Device(
                id=dev_id,
                hostname=dev_id,
                mgmt_ip=nb.ip_address or "unknown",
                platform=nb.platform,
                status=DeviceStatus.PLACEHOLDER,
            )
        )

    return placeholders


def is_in_scope(ip: str, scope_cidr: str | None) -> bool:
    """Return True if ip is within scope_cidr, or scope is None."""
    if scope_cidr is None:
        return True
    try:
        network = ipaddress.ip_network(scope_cidr, strict=False)
        return ipaddress.ip_address(ip) in network
    except ValueError:
        return False


def build_vlan_map(devices: list[Device]) -> list[VlanMapEntry]:
    """Build a network-wide VLAN summary from all discovered devices.

    For each VLAN, shows which devices have it and how many access/trunk
    interfaces are assigned to it.
    """
    # vlan_id → {name, devices set, trunk count, access count}
    vlan_data: dict[str, _VlanBucket] = {}

    for device in devices:
        # Index VLANs declared on this device (from show vlan brief)
        device_vlan_ids: set[str] = set()
        vlan_names: dict[str, str | None] = {}
        for v in device.vlans:
            device_vlan_ids.add(v.vlan_id)
            vlan_names[v.vlan_id] = v.name

        # Count interfaces per VLAN
        for intf in device.interfaces:
            vlan_val = intf.vlan
            if not vlan_val:
                continue

            is_trunk = vlan_val.lower() == "trunk"

            if is_trunk:
                # Trunk port: associate with all VLANs on this device
                for vid in device_vlan_ids:
                    entry = vlan_data.setdefault(
                        vid,
                        {
                            "name": vlan_names.get(vid),
                            "devices": set(),
                            "trunk_ports": 0,
                            "access_ports": 0,
                        },
                    )
                    entry["devices"].add(device.id)
                    entry["trunk_ports"] += 1
            else:
                # Access port: associate with specific VLAN
                entry = vlan_data.setdefault(
                    vlan_val,
                    {
                        "name": vlan_names.get(vlan_val),
                        "devices": set(),
                        "trunk_ports": 0,
                        "access_ports": 0,
                    },
                )
                entry["devices"].add(device.id)
                entry["access_ports"] += 1

        # Ensure VLANs with no interfaces still appear (from show vlan brief)
        for vid in device_vlan_ids:
            if vid not in vlan_data:
                vlan_data[vid] = {
                    "name": vlan_names.get(vid),
                    "devices": set(),
                    "trunk_ports": 0,
                    "access_ports": 0,
                }
            vlan_data[vid]["devices"].add(device.id)

    # Build sorted result
    result = []
    for vid in sorted(vlan_data, key=lambda x: int(x) if x.isdigit() else 9999):
        d = vlan_data[vid]
        result.append(
            VlanMapEntry(
                vlan_id=vid,
                name=d["name"],
                devices=sorted(d["devices"]),
                trunk_ports=d["trunk_ports"],
                access_ports=d["access_ports"],
            )
        )
    return result


def _normalize_mac(mac: str) -> str:
    """Normalize a MAC address to lowercase colon-separated format for comparison."""
    # Remove all separators and lowercase
    raw = re.sub(r"[:\-. ]", "", mac.lower())
    if len(raw) != 12:
        return mac.lower()
    # Format as aa:bb:cc:dd:ee:ff
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


def reconcile_placeholders(
    devices: list[Device],
    links: list[Link],
    neighbors: list[NeighborRecord] | None = None,
) -> tuple[list[Device], list[Link]]:
    """Replace placeholder devices with real devices when they share the same mgmt_ip.

    CDP/LLDP often reports neighbors by MAC-based device IDs (e.g. ``0cd5d36624cc``)
    while actual SSH discovery uses the hostname (e.g. ``SW-Zupanc-03``).  When a
    retry or later BFS wave discovers a device that was previously only a placeholder,
    we need to merge them: keep the real device and rewrite links that pointed at
    the placeholder ID.

    When IP matching fails, falls back to Chassis ID MAC → device base_mac matching.
    This handles chassis-ID-only devices (no system name) and multi-chassis stacks.
    """
    # Build IP → real device ID mapping (only for OK devices)
    ip_to_real: dict[str, str] = {}
    for d in devices:
        if d.status == DeviceStatus.OK and d.mgmt_ip and d.mgmt_ip != "unknown":
            ip_to_real[d.mgmt_ip] = d.id

    # Find placeholders whose IP matches a real device
    id_remap: dict[str, str] = {}  # placeholder_id → real_id
    for d in devices:
        if d.status == DeviceStatus.PLACEHOLDER and d.mgmt_ip in ip_to_real:
            real_id = ip_to_real[d.mgmt_ip]
            if real_id != d.id:
                id_remap[d.id] = real_id

    # Fallback: Chassis ID MAC → base_mac matching for remaining placeholders
    if neighbors:
        # Build normalized base_mac → real device ID mapping
        mac_to_real: dict[str, str] = {}
        for d in devices:
            if d.status == DeviceStatus.OK and getattr(d, "base_mac", None):
                mac_to_real[_normalize_mac(d.base_mac)] = d.id  # type: ignore[arg-type]

        if mac_to_real:
            # Build chassis_id → placeholder device_id from neighbor records
            chassis_to_placeholder: dict[str, str] = {}
            for nb in neighbors:
                if nb.chassis_id and nb.chassis_id_subtype == "mac":
                    norm = _normalize_mac(nb.chassis_id)
                    # Only map if the device_id is a placeholder we haven't resolved
                    if nb.device_id not in id_remap:
                        placeholder = next(
                            (
                                d
                                for d in devices
                                if d.id == nb.device_id and d.status == DeviceStatus.PLACEHOLDER
                            ),
                            None,
                        )
                        if placeholder:
                            chassis_to_placeholder[norm] = placeholder.id

            # Match chassis MAC to base MAC
            for chassis_mac, placeholder_id in chassis_to_placeholder.items():
                if chassis_mac in mac_to_real and placeholder_id not in id_remap:
                    real_id = mac_to_real[chassis_mac]
                    if real_id != placeholder_id:
                        id_remap[placeholder_id] = real_id

    if not id_remap:
        return devices, links

    # Remove placeholders that have a real counterpart
    devices = [d for d in devices if d.id not in id_remap]

    # Rewrite links (model_copy preserves LLDP metadata)
    links = [
        lk.model_copy(
            update={
                "source": id_remap.get(lk.source, lk.source),
                "target": id_remap.get(lk.target, lk.target),
            }
        )
        for lk in links
    ]

    return devices, normalize_links(links)


def normalize_interface_name(name: str) -> str:
    """Expand abbreviated interface names to full form (Cisco + Arista EOS)."""
    abbrevs = {
        "Gi": "GigabitEthernet",
        "Fa": "FastEthernet",
        "Te": "TenGigabitEthernet",
        "Hu": "HundredGigE",
        "Fo": "FortyGigabitEthernet",
        "Twe": "TwentyFiveGigE",
        "Eth": "Ethernet",
        "Et": "Ethernet",  # Arista EOS abbreviation
        "Po": "Port-channel",
        "Vl": "Vlan",
        "Lo": "Loopback",
        "Tu": "Tunnel",
        "Mg": "Mgmt",
        "Ma": "Management",  # Arista Management interface
    }
    for abbr, full in abbrevs.items():
        if name.startswith(abbr) and not name.startswith(full):
            return full + name[len(abbr) :]
    return name


# ---------------------------------------------------------------------------
# Speed detection helpers
# ---------------------------------------------------------------------------

_INTF_SPEED_PREFIXES: list[tuple[str, str]] = [
    ("HundredGigE", "100G"),
    ("FortyGigabitEthernet", "40G"),
    ("TwentyFiveGigE", "25G"),
    ("TenGigabitEthernet", "10G"),
    ("GigabitEthernet", "1G"),
    ("FastEthernet", "100M"),
    ("Ethernet", "1G"),
]


def _detect_intf_speed(intf: str) -> str | None:
    norm = normalize_interface_name(intf)
    for prefix, speed in _INTF_SPEED_PREFIXES:
        if norm.startswith(prefix):
            return speed
    return None


def _speed_label(group: list[Link]) -> str | None:
    speeds = [s for lk in group if (s := _detect_intf_speed(lk.source_intf)) is not None]
    if not speeds:
        return None
    n = len(group)
    return f"{n}x{speeds[0]}" if len(set(speeds)) == 1 else f"{n} members"


# ---------------------------------------------------------------------------
# Port-channel link collapsing
# ---------------------------------------------------------------------------


def collapse_port_channel_links(
    links: list[Link],
    devices: list[Device],
) -> list[Link]:
    """Collapse multiple port-channel member links into a single labeled edge.

    When two devices are connected via EtherChannel/LACP, CDP/LLDP reports one
    link per member interface. This function detects those groups (using
    per-device EtherChannel data) and replaces them with a single Link whose
    ``source_intf``/``target_intf`` are the port-channel names, plus a
    ``members`` list so the frontend can expand them on click.

    Links that cannot be attributed to a port-channel are left unchanged.
    Groups with only a single link are also left unchanged (nothing to collapse).
    """
    # Build per-device: normalized member interface → EtherChannelInfo
    device_member_map: dict[str, dict[str, EtherChannelInfo]] = {}
    for device in devices:
        member_map: dict[str, EtherChannelInfo] = {}
        for ec in device.etherchannels:
            for member in ec.members:
                member_map[normalize_interface_name(member.interface)] = ec
        device_member_map[device.id] = member_map

    # Group links by (frozenset({src_id, tgt_id}), port_channel_name)
    # Port-channel name is taken from whichever side has EC data (source preferred).
    groups: dict[tuple[frozenset[str], str], list[Link]] = defaultdict(list)
    ungrouped: list[Link] = []

    for link in links:
        src_map = device_member_map.get(link.source, {})
        matched: EtherChannelInfo | None = src_map.get(normalize_interface_name(link.source_intf))
        if matched is None:
            tgt_map = device_member_map.get(link.target, {})
            matched = tgt_map.get(normalize_interface_name(link.target_intf or ""))
        if matched is None:
            ungrouped.append(link)
        else:
            key: tuple[frozenset[str], str] = (
                frozenset({link.source, link.target}),
                matched.port_channel,
            )
            groups[key].append(link)

    result = list(ungrouped)

    for (_pair, po_name), group in groups.items():
        if len(group) == 1:
            # Single link attributed to a port-channel — nothing to collapse
            result.append(group[0])
            continue

        rep = group[0]

        # Find the port-channel name on the target side (may differ, e.g. Po2)
        tgt_map = device_member_map.get(rep.target, {})
        tgt_po: str | None = None
        for lk in group:
            ec_tgt = tgt_map.get(normalize_interface_name(lk.target_intf or ""))
            if ec_tgt:
                tgt_po = ec_tgt.port_channel
                break
        if tgt_po is None:
            tgt_po = po_name  # fallback: assume same name on both sides

        result.append(
            rep.model_copy(
                update={
                    "source_intf": po_name,
                    "target_intf": tgt_po,
                    "port_channel": po_name,
                    "member_count": len(group),
                    "speed_label": _speed_label(group),
                    "members": [
                        LinkMember(source_intf=lk.source_intf, target_intf=lk.target_intf)
                        for lk in group
                    ],
                }
            )
        )

    return result
