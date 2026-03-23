"""Multi-vendor CDP/LLDP/version/interface regex parsers — pure functions."""

from __future__ import annotations

import re

from backend.models import (
    ArpEntry,
    ChannelMember,
    EtherChannelInfo,
    EVPNNeighbor,
    InterfaceInfo,
    InventoryItem,
    MacTableEntry,
    NeighborRecord,
    NVEPeer,
    RouteEntry,
    STPPortInfo,
    STPVlanInfo,
    TrunkInfo,
    VersionInfo,
    VlanInfo,
    VNIMapping,
)
from backend.normalizer import normalize_interface_name

# ---------------------------------------------------------------------------
# Module-level compiled regex constants
# ---------------------------------------------------------------------------

# --- parse_cdp_neighbors ---
_CDP_ENTRY_SPLIT = re.compile(r"-{3,}")
_CDP_DEVICE_ID = re.compile(r"Device[\s\-]ID:\s*(\S+)")
_CDP_ENTRY_ADDR_DOTALL = re.compile(
    r"Entry address\(es\):.*?IP(?:v4)? [Aa]ddress:\s*(\d{1,3}(?:\.\d{1,3}){3})",
    re.DOTALL | re.IGNORECASE,
)
_CDP_MGMT_ADDR_DOTALL = re.compile(
    r"Management address\(es\):.*?IP(?:v4)? [Aa]ddress:\s*(\d{1,3}(?:\.\d{1,3}){3})",
    re.DOTALL | re.IGNORECASE,
)
_CDP_PRIMARY_MGMT_ADDR = re.compile(
    r"Primary Management Address:\s*IP\s+(\d{1,3}(?:\.\d{1,3}){3})",
    re.IGNORECASE,
)
_CDP_ADDRESSES_DOTALL = re.compile(
    r"Addresses:.*?IP\s+(\d{1,3}(?:\.\d{1,3}){3})",
    re.DOTALL | re.IGNORECASE,
)
_CDP_IP_ADDRESS = re.compile(
    r"IP(?:v4)? [Aa]ddress:\s*(\d{1,3}(?:\.\d{1,3}){3})",
    re.IGNORECASE,
)
_CDP_LOCAL_INTF = re.compile(r"Interface:\s*(\S+),")
_CDP_REMOTE_INTF = re.compile(r"Port ID \(outgoing port\):\s*(\S+)")
_CDP_PLATFORM = re.compile(r"Platform:\s*([^,\n]+)")

# --- _parse_lldp_capabilities ---
_LLDP_ENABLED_CAPS = re.compile(r"Enabled Capabilities:\s*(.+)")
_LLDP_SYSTEM_CAPS = re.compile(r"System Capabilities:\s*(.+)")
_LLDP_SUPPORTED_CAPS = re.compile(r"Supported capabilities\s*:\s*(.+)")
_LLDP_CAP_SPLIT = re.compile(r"[,\s]+")

# --- _infer_chassis_id_subtype / _infer_port_id_subtype ---
_CHASSIS_MAC_COLON = re.compile(r"([0-9a-fA-F]{2}[:\-.]){5}[0-9a-fA-F]{2}$")
_CHASSIS_MAC_DOT = re.compile(r"[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}$")
_CHASSIS_NETWORK_ADDR = re.compile(r"\d{1,3}(\.\d{1,3}){3}$")
_PORT_MAC_COLON = re.compile(r"([0-9a-fA-F]{2}[:\-.]){5}[0-9a-fA-F]{2}$")
_PORT_MAC_DOT = re.compile(r"[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}$")
_PORT_LOCAL = re.compile(r"\d+$")
_PORT_IFNAME = re.compile(r"(?:Gi|Te|Fa|Eth|eth|ge|xe|Po|et)")

# --- _parse_lldp_med_tlvs ---
_MED_DEVICE_TYPE = re.compile(r"(?:MED\s+)?Device\s+[Tt]ype:\s*(.+)")
_MED_POE_REQ_WATTS = re.compile(r"Power requested:\s*([\d.]+)\s*(?:W|Watts)", re.IGNORECASE)
_MED_POE_REQ_MW = re.compile(r"(?:PoE\s+)?[Pp]ower requested:\s*(\d+)\s*mW")
_MED_POE_ALLOC_WATTS = re.compile(r"Power allocated:\s*([\d.]+)\s*(?:W|Watts)", re.IGNORECASE)
_MED_POE_ALLOC_MW = re.compile(r"(?:PoE\s+)?[Pp]ower allocated:\s*(\d+)\s*mW")
_MED_NETWORK_POLICY = re.compile(r"Network Policy:\s*(.+)")

# --- _parse_lldp_vlan_tlvs ---
_LLDP_VLAN_ID = re.compile(r"(?:Port\s+)?(?:VLAN|Vlan)\s+ID:\s*(\d+)", re.IGNORECASE)
_LLDP_PVID = re.compile(r"PVID:\s*(\d+)")
_LLDP_VLAN_NAME = re.compile(r"VLAN\s+Name:\s*(\S+.+\S)", re.IGNORECASE)

# --- _parse_lldp_lag_tlvs ---
_LLDP_LAG_LINE = re.compile(r"Link [Aa]ggregation:\s*(.+)")
_LLDP_LAG_PORT_ID = re.compile(r"(?:Aggregated Port|Port Channel)\s+ID:\s*(\d+)")
_LLDP_LAG_SUPPORTED = re.compile(r"Aggregation supported:\s*(\w+)", re.IGNORECASE)
_LLDP_LAG_ENABLED = re.compile(r"Aggregation enabled:\s*(\w+)", re.IGNORECASE)

# --- _parse_lldp_entry_common ---
_LLDP_SYSTEM_NAME = re.compile(r"System Name:[^\S\n]*(\S+)")
_LLDP_CHASSIS_ID = re.compile(r"Chassis [Ii]d:\s*(\S+)")
_LLDP_MGMT_ADDR = re.compile(
    r"Management Addresses.*?IP:\s*(\d{1,3}(?:\.\d{1,3}){3})",
    re.DOTALL | re.IGNORECASE,
)
_LLDP_IPV4 = re.compile(r"IP(?:v4)?:\s*(\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE)
_LLDP_LOCAL_INTF = re.compile(r"Local Intf(?:erface)?:\s*(\S+)")
_LLDP_PORT_ID = re.compile(r"Port id:\s*(\S+)")
_LLDP_SYSTEM_DESC = re.compile(r"System Description:.*?(\S[\w\- .]+\S)\s*\n", re.DOTALL)
_LLDP_PORT_DESC = re.compile(r"Port Description:\s*(.+)")

# --- _parse_junos_lldp_entry ---
_JUNOS_LOCAL_INTF = re.compile(r"Local Interface\s*:\s*(\S+)")
_JUNOS_CHASSIS_ID = re.compile(r"Chassis ID\s*:\s*(\S+)")
_JUNOS_SYSTEM_NAME = re.compile(r"System [Nn]ame\s*:\s*(\S+)")
_JUNOS_PORT_ID = re.compile(r"Port ID\s*:\s*(\S+)")
_JUNOS_PORT_DESC = re.compile(r"Port [Dd]escription\s*:\s*(.+)")
_JUNOS_SYSTEM_DESC = re.compile(r"System [Dd]escription\s*:\s*(\S[\w\- .]+\S)")
_JUNOS_MGMT_ADDR = re.compile(r"Management [Aa]ddress\s*:\s*(\d{1,3}(?:\.\d{1,3}){3})")

# --- _parse_hp_lldp_entry ---
_HP_LOCAL_PORT = re.compile(r"LocalPort\s*:\s*(\S+)")
_HP_LOCAL_PORT_ALT = re.compile(r"Local Port\s*:\s*(\S+)")
_HP_CHASSIS_ID = re.compile(r"ChassisId\s*:\s*(.+)")
_HP_CHASSIS_MAC_SPACE = re.compile(r"[0-9a-fA-F]{2}(\s+[0-9a-fA-F]{2}){5}$")
_HP_SYS_NAME = re.compile(r"SysName\s*:\s*(\S+)")
_HP_PORT_ID = re.compile(r"PortId\s*:\s*(\S+)")
_HP_PORT_DESCR = re.compile(r"PortDescr\s*:\s*(.+)")
_HP_SYS_DESCR = re.compile(r"SysDescr\s*:\s*(\S[\w\- .]+\S)")
_HP_MGMT_ADDR = re.compile(
    r"(?:Mgmt(?:Addr|IP)|Address)\s*:\s*(\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE
)

# --- detect_lldp_platform ---
_DETECT_HP = re.compile(r"(?:LocalPort|ChassisId)\s*:")
_DETECT_CISCO = re.compile(r"(?:Chassis id:|Local Intf:)")
_DETECT_JUNOS = re.compile(r"(?:Local Interface\s*:|Chassis ID\s*:)")

# --- parse_lldp_neighbors ---
_LLDP_ENTRY_SPLIT = re.compile(r"\n\s*\n|\n-{3,}")
_LLDP_CISCO_SPLIT = re.compile(r"-{3,}")

# --- parse_show_version ---
_VERSION_HOSTNAME_UPTIME = re.compile(r"^(\S+)\s+uptime", re.MULTILINE)
_VERSION_DEVICE_NAME = re.compile(r"Device name:\s*(\S+)", re.IGNORECASE)
_VERSION_HOSTNAME = re.compile(r"hostname\s+(\S+)", re.IGNORECASE)
_VERSION_PLATFORM_PROC = re.compile(
    r"[Cc]isco\s+([\w\-]+(?:\s+\([\w\-]+\))?)\s+(?:processor|chassis|bytes)"
)
_VERSION_MODEL_NUMBER = re.compile(r"Model number\s*:\s*(\S+)")
_VERSION_PLATFORM_C = re.compile(r"[Cc]isco\s+(C\d{4}[\w\-]*)")
_VERSION_PLATFORM_NEXUS = re.compile(r"[Cc]isco\s+(Nexus\s*\d+\S*)")
_VERSION_PLATFORM_NK = re.compile(r"[Cc]isco\s+(N\d[Kk][\w\-]*)")
_VERSION_SERIAL = re.compile(r"[Ss]ystem [Ss]erial [Nn]umber\s*:\s*(\S+)")
_VERSION_PROC_BOARD_ID = re.compile(r"Processor [Bb]oard ID\s+(\S+)")
_VERSION_IOS_XE = re.compile(
    r"Cisco IOS.*?(?:Software|XE Software)[^\n]*Version\s+([\w\d\.\(\)]+)",
    re.IGNORECASE,
)
_VERSION_NXOS = re.compile(r"(?:NXOS|system):\s+version\s+([\w\d\.\(\)]+)", re.IGNORECASE)
_VERSION_NXOS_ALT = re.compile(r"NX-OS.*?[Vv]ersion\s+([\w\d\.\(\)]+)", re.IGNORECASE)
_VERSION_C1200 = re.compile(r"^\s*Version:\s+([\d.]+)", re.MULTILINE)
_VERSION_UPTIME = re.compile(r"uptime is\s+(.+)", re.IGNORECASE)
_VERSION_KERNEL_UPTIME = re.compile(r"[Kk]ernel uptime is\s+(.+)")
_VERSION_BASE_MAC = re.compile(
    r"(?:Base|System)\s+(?:Ethernet\s+)?MAC\s+Address\s*[:\s]+"
    r"([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})",
    re.IGNORECASE,
)

# --- parse_interfaces_status ---
_INTF_PORT_HEADER = re.compile(r"\s*Port\s+", re.IGNORECASE)
_INTF_SEPARATOR = re.compile(r"^[\s-]+$")
_INTF_ALPHA_START = re.compile(r"[A-Za-z]")

# --- parse_ip_interface_brief / build_interface_ip_map ---
_IP_BRIEF_HEADER = re.compile(r"\s*Interface\s+IP-Address", re.IGNORECASE)
_IP_BRIEF_ALPHA = re.compile(r"[A-Za-z]")
_IP_BRIEF_ADDR = re.compile(r"\d+\.\d+\.\d+\.\d+")

# --- parse_vlan_brief ---
_VLAN_HEADER = re.compile(r"\s*VLAN\s+Name", re.IGNORECASE)
_VLAN_CBS_DETECT = re.compile(r"Tagged|Untagged|Created", re.IGNORECASE)
_VLAN_SEPARATOR = re.compile(r"-{3,}")
_VLAN_ID = re.compile(r"^\d+$")

# --- parse_arp_table ---
# MAC address pattern (shared by ARP and MAC table parsers)
_MAC_PAT = (
    r"(?:[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}"
    r"|[0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}"
    r"[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})"
)
_ARP_IOS_XE = re.compile(
    r"\s*Internet\s+"
    r"(\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(\S+)\s+"
    rf"({_MAC_PAT})\s+"
    r"(\S+)\s+"
    r"(\S+)"
)
_ARP_CBS = re.compile(
    r"\s*(\d{1,3}(?:\.\d{1,3}){3})\s+"
    rf"({_MAC_PAT})\s+"
    r"(\d+)\s+"
    r"(Static|Dynamic)",
    re.IGNORECASE,
)
_ARP_NXOS = re.compile(
    r"\s*(\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(\S+)\s+"
    rf"({_MAC_PAT})\s+"
    r"(\S+)"
)

# --- parse_mac_address_table ---
_MAC_TABLE_ROW = re.compile(
    r"\s*\*?\s*(\d+)\s+"
    rf"({_MAC_PAT})\s+"
    r"(\S+)"
    r".*?\s+"
    r"(\S+)\s*$"
)
_MAC_TABLE_ALPHA = re.compile(r"[A-Za-z]")
_MAC_TABLE_PSEUDO = re.compile(r"(?:CPU|Router|Switch|Drop|Management)", re.IGNORECASE)

# --- parse_ip_route ---
_ROUTE_ACTIVE_DETECT = re.compile(r"\bactive\b")
_ROUTE_CBS_DETECT = re.compile(r"directly connected, vlan\s+\d+", re.IGNORECASE)
_ROUTE_IOS_CONNECTED = re.compile(
    r"\s*([A-Z])\*?\s+"
    r"(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\s+"
    r"is directly connected,\s*(\S+)"
)
_ROUTE_IOS_VIA = re.compile(
    r"\s*([A-Z])\s*\*?\s*(?:[A-Z]{1,2}\s+)?"
    r"(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\s+"
    r"\[(\d+/\d+)\]\s+"
    r"via\s+(\d{1,3}(?:\.\d{1,3}){3})"
    r"(?:,\s*(?:\d[\d:]+,\s*)?(\S+))?"
)

# --- _parse_ip_route_nxos ---
_ROUTE_NXOS_DEST = re.compile(r"\s*(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}),\s*ubest/mbest:")
_ROUTE_NXOS_VIA = re.compile(r"\s+\*?via\s+(\d{1,3}(?:\.\d{1,3}){3})\s*,?\s*(.*)")
_ROUTE_NXOS_METRIC = re.compile(r"\[(\d+/\d+)\]")
_ROUTE_NXOS_AGE = re.compile(r"\d[\d:dhwm]+$")
_ROUTE_NXOS_INTF_SLASH = re.compile(r"[A-Za-z]")
_ROUTE_NXOS_INTF_PREFIX = re.compile(r"(?i)(vlan|loopback|lo|mgmt)\d")
_ROUTE_NXOS_RTYPE = re.compile(r"[a-z][\w-]*$", re.IGNORECASE)

# --- _parse_ip_route_cbs ---
_ROUTE_CBS_CONNECTED = re.compile(
    r"\s*([A-Z])\s+"
    r"(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\s+"
    r"directly connected,\s*vlan\s+(\d+)",
    re.IGNORECASE,
)
_ROUTE_CBS_VIA = re.compile(
    r"\s*([A-Z])\s+"
    r"(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\s+"
    r"via\s+(\d{1,3}(?:\.\d{1,3}){3})"
)

# --- parse_etherchannel_summary ---
_EC_SEPARATOR = re.compile(r"^-{3,}[\s+\-]*$")
_EC_CHANNEL_ID = re.compile(r"\s*(\d+)\s+")
_EC_PO_MATCH = re.compile(r"(Po\d+)\(([A-Za-z]+)\)")
_EC_PROTOCOL = re.compile(r"\b(LACP|PAgP|NONE)\b", re.IGNORECASE)
_EC_MEMBER = re.compile(r"(\S+?)\(([A-Za-z])\)")

# --- parse_nve_peers ---
_NVE_PEERS_HEADER = re.compile(r"\s*Interface\s+Peer-IP", re.IGNORECASE)
_NVE_BLANK_OR_DASH = re.compile(r"^[\s-]+$")

# --- parse_nve_vni ---
_NVE_VNI_HEADER = re.compile(r"\s*Interface\s+VNI", re.IGNORECASE)
_NVE_VNI_TYPE = re.compile(r"(L[23])\s+\[([^\]]+)\]")

# --- parse_bgp_evpn_summary ---
_BGP_EVPN_HEADER = re.compile(r"\s*Neighbor\s+V\s+AS", re.IGNORECASE)
_BGP_EVPN_IP = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")

# --- parse_spanning_tree ---
_STP_VLAN_SPLIT = re.compile(r"(?=^VLAN\d+)", re.MULTILINE)
_STP_VLAN_MATCH = re.compile(r"VLAN(\d+)")
_STP_PROTOCOL = re.compile(r"protocol\s+(\S+)", re.IGNORECASE)
_STP_IS_ROOT = re.compile(r"This bridge is the root", re.IGNORECASE)
_STP_ROOT_PRIORITY = re.compile(r"Root ID\s+Priority\s+(\d+)")
_STP_ROOT_ADDRESS = re.compile(r"Root ID\s+Priority\s+\d+\s+Address\s+(\S+)")
_STP_ROOT_COST = re.compile(r"Root ID.*?Cost\s+(\d+)", re.DOTALL)
_STP_BRIDGE_PRIORITY = re.compile(r"Bridge ID\s+Priority\s+(\d+)")
_STP_BRIDGE_ADDRESS = re.compile(r"Bridge ID\s+Priority\s+\d+.*?Address\s+(\S+)", re.DOTALL)
_STP_INTF_HEADER = re.compile(r"^-{3,}.*$", re.MULTILINE)
_STP_DASH_LINE = re.compile(r"^-{3,}$")
_STP_BLANK_LINE = re.compile(r"^\s*$")
_STP_PORT_FULL = re.compile(
    r"(\S+)\s+"
    r"(Root|Desg|Altn|Back|Mstr)\s+"
    r"(FWD|BLK|LRN|LIS|DIS)\s+"
    r"(\d+)\s+"
    r"(\S+)\s+"
    r"(.+?)\s*$"
)
_STP_PORT_MINIMAL = re.compile(
    r"(\S+)\s+"
    r"(Root|Desg|Altn|Back|Mstr)\s+"
    r"(FWD|BLK|LRN|LIS|DIS)\s+"
    r"(\d+)"
)

# --- parse_inventory ---
_INV_NAME_DESCR = re.compile(r'NAME:\s+"([^"]*)".*?DESCR:\s+"([^"]*)"')
_INV_PID = re.compile(r"PID:\s+(\S+)")
_INV_VID = re.compile(r"VID:\s+(\S+)")
_INV_SN = re.compile(r"SN:\s+(\S+)")

# --- parse_interfaces_trunk ---
_TRUNK_SEPARATOR = re.compile(r"^-{3,}")
_TRUNK_ALPHA = re.compile(r"[A-Za-z]")

# ---------------------------------------------------------------------------
# CDP
# ---------------------------------------------------------------------------


def parse_cdp_neighbors(output: str) -> list[NeighborRecord]:
    """Parse `show cdp neighbors detail` output into NeighborRecord list."""
    records: list[NeighborRecord] = []

    # Split on the CDP entry separator
    entries = _CDP_ENTRY_SPLIT.split(output)

    for entry in entries:
        if "Device ID" not in entry and "Device-ID" not in entry:
            continue

        # IOS-XE: "Device ID: hostname"  CBS/C1200: "Device-ID: hostname"
        device_id = _extract(_CDP_DEVICE_ID, entry)
        if not device_id:
            continue

        # Strip domain suffix from device_id if present (keep base hostname)
        device_id = device_id.split(".")[0]

        # Try multiple Cisco CDP IP formats (varies by IOS version / platform)
        ip_address = (
            _extract(_CDP_ENTRY_ADDR_DOTALL, entry)
            or _extract(_CDP_MGMT_ADDR_DOTALL, entry)
            # CBS/C1200: "Primary Management Address: IP 10.0.0.1"
            or _extract(_CDP_PRIMARY_MGMT_ADDR, entry)
            # CBS/C1200: "Addresses:\n          IP 10.0.0.1"
            or _extract(_CDP_ADDRESSES_DOTALL, entry)
            # Generic fallback
            or _extract(_CDP_IP_ADDRESS, entry)
        )

        local_intf = _extract(_CDP_LOCAL_INTF, entry)
        remote_intf = _extract(_CDP_REMOTE_INTF, entry)
        platform = _extract(_CDP_PLATFORM, entry)
        if platform:
            platform = platform.strip()

        records.append(
            NeighborRecord(
                device_id=device_id,
                ip_address=ip_address,
                local_interface=local_intf or "",
                remote_interface=remote_intf,
                platform=platform,
                protocol="CDP",
            )
        )

    return records


# ---------------------------------------------------------------------------
# LLDP — multi-vendor parser with TLV extensions
# ---------------------------------------------------------------------------


_LLDP_CAPABILITY_MAP: dict[str, str] = {
    "B": "bridge",
    "R": "router",
    "S": "station",
    "T": "telephone",
    "W": "wlan-ap",
    "P": "repeater",
    "C": "docsis-cable",
    "O": "other",
}

# JunOS uses full words for capabilities
_JUNOS_CAPABILITY_MAP: dict[str, str] = {
    "Bridge": "bridge",
    "Router": "router",
    "Station Only": "station",
    "Telephone": "telephone",
    "WLAN Access Point": "wlan-ap",
    "Repeater": "repeater",
    "DOCSIS Cable Device": "docsis-cable",
    "Other": "other",
}

# LLDP-MED device type mapping
_MED_DEVICE_TYPE_MAP: dict[str, str] = {
    "1": "class-i",
    "2": "class-ii",
    "3": "class-iii",
    "I": "class-i",
    "II": "class-ii",
    "III": "class-iii",
    "Class I": "class-i",
    "Class II": "class-ii",
    "Class III": "class-iii",
    "Endpoint Class I": "class-i",
    "Endpoint Class II": "class-ii",
    "Endpoint Class III": "class-iii",
    "Network Connectivity": "class-i",
}


def _parse_lldp_capabilities(entry: str) -> list[str]:
    """Extract enabled LLDP system capabilities from an entry block."""
    # Prefer "Enabled Capabilities" over "System Capabilities"
    cap_str = _extract(_LLDP_ENABLED_CAPS, entry)
    if not cap_str:
        cap_str = _extract(_LLDP_SYSTEM_CAPS, entry)
    if not cap_str:
        # JunOS: "Supported capabilities : Router Bridge"
        cap_str = _extract(_LLDP_SUPPORTED_CAPS, entry)
    if not cap_str:
        return []
    caps: list[str] = []
    for token in _LLDP_CAP_SPLIT.split(cap_str.strip()):
        token = token.strip()
        if token in _LLDP_CAPABILITY_MAP:
            caps.append(_LLDP_CAPABILITY_MAP[token])
        elif token in _JUNOS_CAPABILITY_MAP:
            caps.append(_JUNOS_CAPABILITY_MAP[token])
        elif token:
            caps.append(token.lower())
    return caps


def _infer_chassis_id_subtype(chassis_id: str) -> str:
    """Infer chassis ID subtype from the value format."""
    if _CHASSIS_MAC_COLON.match(chassis_id):
        return "mac"
    if _CHASSIS_MAC_DOT.match(chassis_id):
        return "mac"
    if _CHASSIS_NETWORK_ADDR.match(chassis_id):
        return "network-addr"
    return "ifName"


def _infer_port_id_subtype(port_id: str) -> str:
    """Infer port ID subtype from the value format."""
    if _PORT_MAC_COLON.match(port_id):
        return "mac"
    if _PORT_MAC_DOT.match(port_id):
        return "mac"
    if _PORT_LOCAL.match(port_id):
        return "local"
    # Interface-like names: Gi0/1, Eth1/49, eth0, ge-0/0/0, xe-0/0/0, etc.
    if _PORT_IFNAME.match(port_id):
        return "ifName"
    return "ifAlias"


def _parse_lldp_med_tlvs(entry: str) -> dict[str, str | float]:
    """Extract LLDP-MED TLV data from an entry block."""
    result: dict[str, str | float] = {}

    # Device type: "MED Device Type: Endpoint Class III" or "Device type: 3"
    dt = _extract(_MED_DEVICE_TYPE, entry)
    if dt:
        dt = dt.strip()
        result["med_device_type"] = _MED_DEVICE_TYPE_MAP.get(dt, dt.lower())

    # PoE requested: "Power requested: 15.4 Watts" or "PoE requested: 15400 mW"
    poe_req = _extract(_MED_POE_REQ_WATTS, entry)
    if not poe_req:
        poe_mw = _extract(_MED_POE_REQ_MW, entry)
        if poe_mw:
            poe_req = str(float(poe_mw) / 1000.0)
    if poe_req:
        result["med_poe_requested"] = float(poe_req)

    # PoE allocated: "Power allocated: 15.4 Watts"
    poe_alloc = _extract(_MED_POE_ALLOC_WATTS, entry)
    if not poe_alloc:
        poe_mw = _extract(_MED_POE_ALLOC_MW, entry)
        if poe_mw:
            poe_alloc = str(float(poe_mw) / 1000.0)
    if poe_alloc:
        result["med_poe_allocated"] = float(poe_alloc)

    # Network policy: "Network Policy: VLAN 100, DSCP 46"
    np = _extract(_MED_NETWORK_POLICY, entry)
    if np:
        result["med_network_policy"] = np.strip()

    return result


def _parse_lldp_vlan_tlvs(entry: str) -> dict[str, int | str]:
    """Extract 802.1 VLAN TLV data from an entry block."""
    result: dict[str, int | str] = {}

    # Port VLAN ID: "Port VLAN ID: 100" or "PVID: 100" or "Vlan ID: 100"
    vlan_id = _extract(_LLDP_VLAN_ID, entry)
    if not vlan_id:
        vlan_id = _extract(_LLDP_PVID, entry)
    if vlan_id:
        result["vlan_id"] = int(vlan_id)

    # VLAN name: "VLAN Name: Management" or "Port-and-Protocol VLAN Name: Management"
    vlan_name = _extract(_LLDP_VLAN_NAME, entry)
    if vlan_name:
        result["vlan_name"] = vlan_name.strip()

    return result


def _parse_lldp_lag_tlvs(entry: str) -> dict[str, bool | int]:
    """Extract 802.3 Link Aggregation TLV data from an entry block."""
    result: dict[str, bool | int] = {}

    # "Link Aggregation: Supported, Enabled"
    lag_line = _extract(_LLDP_LAG_LINE, entry)
    if lag_line:
        lag_lower = lag_line.lower()
        result["lag_supported"] = "supported" in lag_lower
        result["lag_enabled"] = "enabled" in lag_lower
        # "Aggregated Port ID: 7" or "Port Channel ID: 7"
        lag_id = _extract(_LLDP_LAG_PORT_ID, entry)
        if lag_id:
            result["lag_port_channel_id"] = int(lag_id)
    else:
        # Alternative format: separate lines
        lag_sup = _extract(_LLDP_LAG_SUPPORTED, entry)
        if lag_sup:
            result["lag_supported"] = lag_sup.lower() in ("yes", "true", "supported")
        lag_en = _extract(_LLDP_LAG_ENABLED, entry)
        if lag_en:
            result["lag_enabled"] = lag_en.lower() in ("yes", "true", "enabled")
        lag_id = _extract(_LLDP_LAG_PORT_ID, entry)
        if lag_id:
            result["lag_port_channel_id"] = int(lag_id)

    return result


def _parse_lldp_entry_common(entry: str) -> NeighborRecord | None:
    """Parse a single LLDP neighbor entry (Cisco IOS-XE/NX-OS/IOS-XR format).

    Returns None if the entry is not a valid LLDP neighbor block.
    """
    if "Local Intf" not in entry and "local interface" not in entry.lower():
        return None

    # Match System Name only on the same line (avoid grabbing next-line text)
    device_id = _extract(_LLDP_SYSTEM_NAME, entry)
    chassis_id = _extract(_LLDP_CHASSIS_ID, entry)
    if not device_id:
        device_id = chassis_id
    if not device_id:
        return None

    # Strip FQDN suffix, but not for MAC addresses (Cisco dot-notation)
    if _infer_chassis_id_subtype(device_id) != "mac":
        device_id = device_id.split(".")[0]

    ip_address = _extract(_LLDP_MGMT_ADDR, entry)
    if not ip_address:
        ip_address = _extract(_LLDP_IPV4, entry)

    local_intf = _extract(_LLDP_LOCAL_INTF, entry)
    remote_intf = _extract(_LLDP_PORT_ID, entry)
    platform = _extract(_LLDP_SYSTEM_DESC, entry)
    port_desc = _extract(_LLDP_PORT_DESC, entry)

    chassis_id_subtype = _infer_chassis_id_subtype(chassis_id) if chassis_id else None
    port_id_subtype = _infer_port_id_subtype(remote_intf) if remote_intf else None
    capabilities = _parse_lldp_capabilities(entry)

    # TLV extensions
    med = _parse_lldp_med_tlvs(entry)
    vlan = _parse_lldp_vlan_tlvs(entry)
    lag = _parse_lldp_lag_tlvs(entry)

    return NeighborRecord(
        device_id=device_id,
        ip_address=ip_address,
        local_interface=local_intf or "",
        remote_interface=remote_intf,
        platform=platform,
        protocol="LLDP",
        chassis_id_subtype=chassis_id_subtype,
        port_id_subtype=port_id_subtype,
        capabilities=capabilities,
        port_description=port_desc,
        chassis_id=chassis_id,
        med_device_type=str(med["med_device_type"]) if "med_device_type" in med else None,
        med_poe_requested=float(med["med_poe_requested"]) if "med_poe_requested" in med else None,
        med_poe_allocated=float(med["med_poe_allocated"]) if "med_poe_allocated" in med else None,
        med_network_policy=str(med["med_network_policy"]) if "med_network_policy" in med else None,
        vlan_id=int(vlan["vlan_id"]) if "vlan_id" in vlan else None,
        vlan_name=str(vlan["vlan_name"]) if "vlan_name" in vlan else None,
        lag_supported=lag.get("lag_supported") is True if "lag_supported" in lag else None,
        lag_enabled=lag.get("lag_enabled") is True if "lag_enabled" in lag else None,
        lag_port_channel_id=(
            int(lag["lag_port_channel_id"]) if "lag_port_channel_id" in lag else None
        ),
    )


def _parse_junos_lldp_entry(entry: str) -> NeighborRecord | None:
    """Parse a JunOS ``show lldp neighbors`` detail entry.

    JunOS uses different field labels:
    - ``Local Interface    : ge-0/0/0``
    - ``Chassis ID         : aa:bb:cc:dd:ee:ff``
    - ``Port ID            : ge-0/0/1``
    - ``System Name        : JUNOS-SW-01``
    """
    local_intf = _extract(_JUNOS_LOCAL_INTF, entry)
    if not local_intf:
        return None

    chassis_id = _extract(_JUNOS_CHASSIS_ID, entry)
    device_id = _extract(_JUNOS_SYSTEM_NAME, entry)
    if not device_id:
        device_id = chassis_id
    if not device_id:
        return None

    device_id = device_id.split(".")[0]

    remote_intf = _extract(_JUNOS_PORT_ID, entry)
    port_desc = _extract(_JUNOS_PORT_DESC, entry)
    platform = _extract(_JUNOS_SYSTEM_DESC, entry)
    ip_address = _extract(_JUNOS_MGMT_ADDR, entry)

    chassis_id_subtype = _infer_chassis_id_subtype(chassis_id) if chassis_id else None
    port_id_subtype = _infer_port_id_subtype(remote_intf) if remote_intf else None
    capabilities = _parse_lldp_capabilities(entry)

    med = _parse_lldp_med_tlvs(entry)
    vlan = _parse_lldp_vlan_tlvs(entry)
    lag = _parse_lldp_lag_tlvs(entry)

    return NeighborRecord(
        device_id=device_id,
        ip_address=ip_address,
        local_interface=local_intf,
        remote_interface=remote_intf,
        platform=platform,
        protocol="LLDP",
        chassis_id_subtype=chassis_id_subtype,
        port_id_subtype=port_id_subtype,
        capabilities=capabilities,
        port_description=port_desc,
        chassis_id=chassis_id,
        med_device_type=str(med["med_device_type"]) if "med_device_type" in med else None,
        med_poe_requested=float(med["med_poe_requested"]) if "med_poe_requested" in med else None,
        med_poe_allocated=float(med["med_poe_allocated"]) if "med_poe_allocated" in med else None,
        med_network_policy=str(med["med_network_policy"]) if "med_network_policy" in med else None,
        vlan_id=int(vlan["vlan_id"]) if "vlan_id" in vlan else None,
        vlan_name=str(vlan["vlan_name"]) if "vlan_name" in vlan else None,
        lag_supported=lag.get("lag_supported") is True if "lag_supported" in lag else None,
        lag_enabled=lag.get("lag_enabled") is True if "lag_enabled" in lag else None,
        lag_port_channel_id=(
            int(lag["lag_port_channel_id"]) if "lag_port_channel_id" in lag else None
        ),
    )


def _parse_hp_lldp_entry(entry: str) -> NeighborRecord | None:
    """Parse an HP/Aruba ProCurve ``show lldp info remote-device`` detail entry.

    HP uses different field labels:
    - ``LocalPort : 1``
    - ``ChassisId : 00 11 22 33 44 55``
    - ``PortId    : 2``
    - ``SysName   : HP-SWITCH-01``
    """
    local_intf = _extract(_HP_LOCAL_PORT, entry)
    if not local_intf:
        # Alternative HP format
        local_intf = _extract(_HP_LOCAL_PORT_ALT, entry)
    if not local_intf:
        return None

    # HP may use space-separated MAC: "00 11 22 33 44 55"
    chassis_id_raw = _extract(_HP_CHASSIS_ID, entry)
    chassis_id: str | None = None
    if chassis_id_raw:
        cleaned = chassis_id_raw.strip()
        # Convert space-separated hex to colon-separated
        if _HP_CHASSIS_MAC_SPACE.match(cleaned):
            chassis_id = ":".join(cleaned.split())
        else:
            chassis_id = cleaned

    device_id = _extract(_HP_SYS_NAME, entry)
    if not device_id:
        device_id = chassis_id
    if not device_id:
        return None

    device_id = device_id.split(".")[0]

    remote_intf = _extract(_HP_PORT_ID, entry)
    if not remote_intf:
        remote_intf = _extract(_HP_PORT_DESCR, entry)
    port_desc = _extract(_HP_PORT_DESCR, entry)
    platform = _extract(_HP_SYS_DESCR, entry)
    ip_address = _extract(_HP_MGMT_ADDR, entry)

    chassis_id_subtype = _infer_chassis_id_subtype(chassis_id) if chassis_id else None
    port_id_subtype = _infer_port_id_subtype(remote_intf) if remote_intf else None

    # HP uses "System Capabilities Supported:" and "System Capabilities Enabled:"
    capabilities = _parse_lldp_capabilities(entry)

    return NeighborRecord(
        device_id=device_id,
        ip_address=ip_address,
        local_interface=local_intf,
        remote_interface=remote_intf,
        platform=platform,
        protocol="LLDP",
        chassis_id_subtype=chassis_id_subtype,
        port_id_subtype=port_id_subtype,
        capabilities=capabilities,
        port_description=port_desc,
        chassis_id=chassis_id,
    )


def detect_lldp_platform(output: str) -> str:
    """Detect the LLDP output platform variant from the raw output.

    Returns one of: ``cisco``, ``junos``, ``hp``.
    The ``cisco`` variant covers IOS-XE, NX-OS, IOS-XR, and Arista EOS since
    they all use ``Chassis id:`` field labels (lowercase 'id').
    """
    # HP/Aruba: uses "LocalPort :" or "ChassisId :" pattern (check first, most distinctive)
    if _DETECT_HP.search(output):
        return "hp"
    # Cisco variants (IOS-XE, NX-OS, IOS-XR, EOS): "Chassis id:" (lowercase)
    # Also check for "Local Intf:" which is definitively Cisco
    if _DETECT_CISCO.search(output):
        return "cisco"
    # JunOS: uses "Chassis ID" (uppercase) with "Local Interface :" pattern
    if _DETECT_JUNOS.search(output):
        return "junos"
    # Default: Cisco
    return "cisco"


def parse_lldp_neighbors(output: str, platform: str | None = None) -> list[NeighborRecord]:
    """Parse ``show lldp neighbors detail`` output into NeighborRecord list.

    Supports multiple vendor formats:
    - **Cisco** (IOS-XE, NX-OS, IOS-XR, Arista EOS): ``Local Intf:`` style
    - **Juniper JunOS**: ``Local Interface :`` style
    - **HP/Aruba ProCurve**: ``LocalPort :`` style

    If *platform* is not given, it is auto-detected from the output.
    """
    if platform is None:
        platform = detect_lldp_platform(output)

    records: list[NeighborRecord] = []

    if platform == "junos":
        # JunOS separates entries by blank lines or dashes
        entries = _LLDP_ENTRY_SPLIT.split(output)
        for entry in entries:
            rec = _parse_junos_lldp_entry(entry)
            if rec is not None:
                records.append(rec)
    elif platform == "hp":
        # HP separates entries by blank lines or dashes
        entries = _LLDP_ENTRY_SPLIT.split(output)
        for entry in entries:
            rec = _parse_hp_lldp_entry(entry)
            if rec is not None:
                records.append(rec)
    else:
        # Cisco: entries are separated by "------...------"
        entries = _LLDP_CISCO_SPLIT.split(output)
        for entry in entries:
            rec = _parse_lldp_entry_common(entry)
            if rec is not None:
                records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Show version
# ---------------------------------------------------------------------------


def parse_show_version(output: str) -> VersionInfo:
    """Parse `show version` output.

    Supports IOS-XE, NX-OS, and C1200/Small Business formats.
    """
    # --- Hostname ---
    hostname = _extract(_VERSION_HOSTNAME_UPTIME, output)
    if not hostname:
        # NX-OS: "Device name: NXOS-SWITCH-01"
        hostname = _extract(_VERSION_DEVICE_NAME, output)
    if not hostname:
        hostname = _extract(_VERSION_HOSTNAME, output)
    # Strip FQDN domain suffix to match CDP/LLDP device_id normalisation
    if hostname:
        hostname = hostname.split(".")[0]

    # --- Platform ---
    platform_match = _extract(_VERSION_PLATFORM_PROC, output)
    if not platform_match:
        platform_match = _extract(_VERSION_MODEL_NUMBER, output)
    if not platform_match:
        platform_match = _extract(_VERSION_PLATFORM_C, output)
    if not platform_match:
        # NX-OS: "cisco Nexus9000 C93180YC-FX3" or "cisco Nexus 9000"
        platform_match = _extract(_VERSION_PLATFORM_NEXUS, output)
    if not platform_match:
        # NX-OS hardware line: "  cisco Nexus9000 C93180YC-FX3 Chassis"
        platform_match = _extract(_VERSION_PLATFORM_NK, output)

    # --- Serial ---
    serial = _extract(_VERSION_SERIAL, output)
    if not serial:
        serial = _extract(_VERSION_PROC_BOARD_ID, output)

    # --- OS Version ---
    os_version = _extract(_VERSION_IOS_XE, output)
    if not os_version:
        # NX-OS: "NXOS: version 10.3(1)" or "system:    version 10.3(1)"
        os_version = _extract(_VERSION_NXOS, output)
    if not os_version:
        # NX-OS alternative: "Cisco Nexus Operating System (NX-OS) Software ... version 10.3(1)"
        os_version = _extract(_VERSION_NXOS_ALT, output)
    if not os_version:
        # C1200 / Small Business firmware: "  Version: 4.1.3.36"
        os_version = _extract(_VERSION_C1200, output)

    # --- Uptime ---
    # IOS-XE: "SW-ACCESS-01 uptime is 10 weeks, 3 days, 4 hours, 22 minutes"
    uptime = _extract(_VERSION_UPTIME, output)
    if not uptime:
        # NX-OS: "Kernel uptime is 120 day(s), 3 hour(s), 22 minute(s), 10 second(s)"
        uptime = _extract(_VERSION_KERNEL_UPTIME, output)
    if uptime:
        uptime = uptime.strip().rstrip(".")

    # --- Base MAC ---
    # IOS-XE: "Base Ethernet MAC Address         : 0cd5.d366.2400"
    # NX-OS:  "System MAC Address:  0cd5.d366.2400"
    base_mac = _extract(_VERSION_BASE_MAC, output)

    return VersionInfo(
        hostname=hostname,
        platform=platform_match,
        serial=serial,
        os_version=os_version,
        uptime=uptime,
        base_mac=base_mac,
    )


# ---------------------------------------------------------------------------
# Show interfaces status
# ---------------------------------------------------------------------------


def parse_interfaces_status(output: str) -> list[InterfaceInfo]:
    """Parse ``show interfaces status`` output.

    Handles both IOS-XE format (Port/Name/Status/Vlan/Duplex/Speed/Type) and
    Cisco Small Business / C1200 format (Port/Type/Duplex/Speed/.../State/...).
    Column boundaries are detected dynamically from the header so the parser
    is not sensitive to column order.
    """
    results: list[InterfaceInfo] = []
    lines = output.splitlines()
    known_cols: dict[str, int] = {}  # canonical name → char offset
    all_offsets: list[int] = []  # every column-start position in header
    header_idx = -1

    for i, line in enumerate(lines):
        if _INTF_PORT_HEADER.match(line):
            header_idx = i
            # Detect ALL word-start positions for column boundaries
            in_space = True
            for j, ch in enumerate(line):
                if ch.strip():
                    if in_space:
                        all_offsets.append(j)
                        in_space = False
                else:
                    in_space = True
            # Map the columns we care about
            for col_name in ("Port", "Name", "Status", "State", "Vlan", "Duplex", "Speed", "Type"):
                m = re.search(rf"\b{col_name}\b", line, re.IGNORECASE)
                if m:
                    canonical = col_name.lower()
                    if canonical == "state":
                        canonical = "status"  # C1200 alias
                    known_cols[canonical] = m.start()
            break

    if header_idx < 0:
        return results

    all_offsets.sort()

    def _col(line: str, key: str) -> str | None:
        start = known_cols.get(key)
        if start is None or start >= len(line):
            return None
        # Find next column boundary from all detected positions
        end = None
        for off in all_offsets:
            if off > start:
                end = off
                break
        val = line[start:end].strip() if end else line[start:].strip()
        return val or None

    for line in lines[header_idx + 1 :]:
        if not line.strip():
            break  # stop at blank line (C1200 has a second port-channel table)
        if _INTF_SEPARATOR.match(line):
            continue  # skip separator lines
        port = _col(line, "port")
        if not port or not _INTF_ALPHA_START.match(port):
            continue
        port_val = port.split()[0] if port else port
        results.append(
            InterfaceInfo(
                name=port_val,
                status=_col(line, "status"),
                vlan=_col(line, "vlan"),
                duplex=_col(line, "duplex"),
                speed=_col(line, "speed"),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Show ip interface brief (fallback for routers / devices without
# "show interfaces status")
# ---------------------------------------------------------------------------


def parse_ip_interface_brief(output: str) -> list[InterfaceInfo]:
    """Parse ``show ip interface brief`` output.

    Typical header::

        Interface              IP-Address      OK? Method Status                Protocol
    """
    results: list[InterfaceInfo] = []
    in_data = False

    for line in output.splitlines():
        if _IP_BRIEF_HEADER.match(line):
            in_data = True
            continue
        if not in_data:
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        name = parts[0]
        if not _IP_BRIEF_ALPHA.match(name):
            continue
        ip_addr = parts[1] if parts[1] != "unassigned" else None
        status = parts[4]  # Status column (up/down/administratively)
        protocol = parts[5]  # Protocol column (up/down)
        # Map to the InterfaceInfo shape used everywhere else
        intf_status = "connected" if status == "up" and protocol == "up" else "down"
        results.append(
            InterfaceInfo(
                name=name,
                status=intf_status,
                vlan=None,
                speed=None,
                ip_address=ip_addr,
            )
        )

    return results


# ---------------------------------------------------------------------------
# IP address map from show ip interface brief
# ---------------------------------------------------------------------------


def build_interface_ip_map(output: str) -> dict[str, str]:
    """Extract interface → IP address mapping from ``show ip interface brief``.

    Returns a dict like ``{"Vlan1": "10.0.0.1", "GigabitEthernet1/0/1": "10.0.1.1"}``.
    Used to enrich InterfaceInfo objects collected from other commands.
    """
    ip_map: dict[str, str] = {}
    in_data = False
    for line in output.splitlines():
        if _IP_BRIEF_HEADER.match(line):
            in_data = True
            continue
        if not in_data:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        if not _IP_BRIEF_ALPHA.match(name):
            continue
        ip_addr = parts[1]
        if ip_addr != "unassigned" and _IP_BRIEF_ADDR.match(ip_addr):
            ip_map[name] = ip_addr
    return ip_map


# ---------------------------------------------------------------------------
# Show vlan brief
# ---------------------------------------------------------------------------


def parse_vlan_brief(output: str) -> list[VlanInfo]:
    """Parse ``show vlan brief`` or ``show vlan`` output.

    IOS-XE (show vlan brief)::

        VLAN Name                             Status    Ports
        ---- -------------------------------- --------- -----
        1    default                          active    Gi1/0/3
        10   Data                             active

    CBS / C1200 (show vlan)::

        VLAN  Name                 Tagged Ports    Untagged Ports  Created By
        ----  -------------------  --------------- ---------------  ----------
        1     default                              gi1-10           Default
        10    Management           gi1             gi2,gi3          Manual
    """
    results: list[VlanInfo] = []
    in_data = False
    is_cbs = False

    for line in output.splitlines():
        if _VLAN_HEADER.match(line):
            in_data = True
            # CBS format has "Tagged Ports" / "Untagged Ports" — no Status column
            is_cbs = bool(_VLAN_CBS_DETECT.search(line))
            continue
        if _VLAN_SEPARATOR.match(line.strip()):
            continue
        if not in_data:
            continue
        parts = line.split()
        if not parts:
            continue
        vlan_id = parts[0]
        if not _VLAN_ID.match(vlan_id):
            continue
        name = parts[1] if len(parts) > 1 else None
        # CBS has no Status column — all VLANs shown are active
        status = "active" if is_cbs else (parts[2] if len(parts) > 2 else None)
        results.append(VlanInfo(vlan_id=vlan_id, name=name, status=status))
    return results


# ---------------------------------------------------------------------------
# Show ip arp
# ---------------------------------------------------------------------------


def parse_arp_table(output: str) -> list[ArpEntry]:
    """Parse ``show ip arp`` or ``show arp`` output.

    Typical IOS-XE (show ip arp)::

        Protocol  Address          Age (min)  Hardware Addr   Type   Interface
        Internet  10.0.0.1                -   0cd5.d366.24cc  ARPA   Vlan1
        Internet  10.0.0.10              12   aabb.ccdd.eeff  ARPA   Vlan1

    NX-OS::

        Address         Age       MAC Address     Interface
        10.0.0.1        00:02:30  0cd5.d366.24cc  Vlan1

    CBS / C1200 (show arp)::

        IP address        MAC address        VLAN     Type       Age (m)
        -----------------------------------------------------------------
        192.168.30.1      00-1e-49-e3-52-cc  1        Dynamic    2
        192.168.30.100    c8-4b-d6-aa-bb-cc  30       Static     -
    """
    results: list[ArpEntry] = []

    for line in output.splitlines():
        # IOS-XE format: "Internet  IP  Age  MAC  Type  Interface"
        m = _ARP_IOS_XE.match(line)
        if m:
            age = m.group(2)
            entry_type = "static" if age == "-" else "dynamic"
            results.append(
                ArpEntry(
                    ip_address=m.group(1),
                    mac_address=m.group(3),
                    interface=m.group(5),
                    entry_type=entry_type,
                )
            )
            continue

        # CBS / C1200 format: "IP  MAC  VLAN  Type  Age"
        # e.g. "192.168.30.1  00-1e-49-e3-52-cc  1  Dynamic  2"
        m = _ARP_CBS.match(line)
        if m:
            entry_type = m.group(4).lower()
            results.append(
                ArpEntry(
                    ip_address=m.group(1),
                    mac_address=m.group(2),
                    interface=f"Vlan{m.group(3)}",
                    entry_type=entry_type,
                )
            )
            continue

        # NX-OS format: "IP  Age  MAC  Interface"
        m = _ARP_NXOS.match(line)
        if m:
            results.append(
                ArpEntry(
                    ip_address=m.group(1),
                    mac_address=m.group(3),
                    interface=m.group(4),
                    entry_type="dynamic",
                )
            )

    return results


# ---------------------------------------------------------------------------
# Show mac address-table
# ---------------------------------------------------------------------------


def parse_mac_address_table(output: str) -> list[MacTableEntry]:
    """Parse ``show mac address-table`` output.

    IOS-XE::

          Vlan    Mac Address       Type        Ports
        ----    -----------       --------    -----
          10    aabb.ccdd.eeff    DYNAMIC     Gi1/0/1
           1    0cd5.d366.24cc    STATIC      Vl1

    NX-OS::

        * 10     aabb.ccdd.eeff   dynamic  0         F    F  Eth1/1

    CBS / C1200 (hyphen MAC notation)::

          VLAN   MAC address         Port type    Ports
          -----  -----------------   ----------  -------
          1      00-1e-49-e3-52-cc   Dynamic      gi1
          10     88-94-71-e5-85-4c   Dynamic      gi2
    """
    results: list[MacTableEntry] = []

    for line in output.splitlines():
        # IOS-XE / NX-OS / CBS: optional leading spaces/star, VLAN, MAC, Type, Port
        m = _MAC_TABLE_ROW.match(line)
        if m:
            port = m.group(4)
            # Skip CPU/Router/Switch/Management entries and placeholder "--"
            is_alpha = _MAC_TABLE_ALPHA.match(port)
            is_pseudo = _MAC_TABLE_PSEUDO.match(port)
            if is_alpha and not is_pseudo:
                results.append(
                    MacTableEntry(
                        vlan_id=m.group(1),
                        mac_address=m.group(2),
                        entry_type=m.group(3).lower(),
                        interface=port,
                    )
                )

    return results


# ---------------------------------------------------------------------------
# Show ip route
# ---------------------------------------------------------------------------

_ROUTE_TYPE_MAP: dict[str, str] = {
    "C": "connected",
    "L": "local",
    "S": "static",
    "O": "ospf",
    "B": "bgp",
    "D": "eigrp",
    "R": "rip",
}


def parse_ip_route(output: str) -> list[RouteEntry]:
    """Parse ``show ip route`` output.

    Handles IOS-XE, NX-OS, and CBS/C1200 formats.

    IOS-XE::

        C        10.0.0.0/24 is directly connected, Vlan1
        S        10.1.0.0/16 [1/0] via 10.0.0.254
        S*    0.0.0.0/0 [1/0] via 10.0.0.1
        O        10.2.0.0/24 [110/2] via 10.0.0.2, 00:05:30, Vlan1

    NX-OS::

        10.0.0.0/24, ubest/mbest: 1/0, attached
            *via 10.0.0.1, Vlan1, [0/0], 2d03h, direct
        10.1.0.0/16, ubest/mbest: 1/0
            *via 10.0.0.254, [1/0], 01:30:00, static

    CBS/C1200::

        S   0.0.0.0/0        via 192.168.1.1                  active
        C   192.168.1.0/24        directly connected, vlan 1   active
    """
    results: list[RouteEntry] = []

    # ---- Detect NX-OS format (has "ubest/mbest" lines) ----
    if "ubest/mbest" in output:
        return _parse_ip_route_nxos(output)

    # ---- Detect CBS/C1200 format (has "active" status column) ----
    if _ROUTE_ACTIVE_DETECT.search(output) and _ROUTE_CBS_DETECT.search(output):
        return _parse_ip_route_cbs(output)

    # ---- IOS-XE format ----
    for line in output.splitlines():
        # Connected/local: "C  10.0.0.0/24 is directly connected, Vlan1"
        m = _ROUTE_IOS_CONNECTED.match(line)
        if m:
            code = m.group(1)
            results.append(
                RouteEntry(
                    protocol=code,
                    route_type=_ROUTE_TYPE_MAP.get(code, code.lower()),
                    destination=m.group(2),
                    next_hop=None,
                    interface=m.group(3),
                    metric=None,
                )
            )
            continue

        # Via route: "S  10.1.0.0/16 [1/0] via 10.0.0.254, Vlan1"
        # Also handles OSPF with age: "O  10.2.0.0/24 [110/2] via 10.0.0.2, 00:05:30, Vlan1"
        m = _ROUTE_IOS_VIA.match(line)
        if m:
            code = m.group(1)
            results.append(
                RouteEntry(
                    protocol=code,
                    route_type=_ROUTE_TYPE_MAP.get(code, code.lower()),
                    destination=m.group(2),
                    next_hop=m.group(4),
                    interface=m.group(5),
                    metric=m.group(3),
                )
            )
            continue

    return results


# NX-OS route type keywords → canonical type
_NXOS_ROUTE_TYPE_MAP: dict[str, str] = {
    "direct": "connected",
    "local": "local",
    "static": "static",
    "ospf": "ospf",
    "bgp": "bgp",
    "eigrp": "eigrp",
    "rip": "rip",
}

# NX-OS route type → protocol code letter
_NXOS_PROTO_CODE: dict[str, str] = {
    "direct": "C",
    "local": "L",
    "static": "S",
    "ospf": "O",
    "bgp": "B",
    "eigrp": "D",
    "rip": "R",
}


def _parse_ip_route_nxos(output: str) -> list[RouteEntry]:
    """Parse NX-OS ``show ip route`` output.

    NX-OS format uses a destination header line followed by ``*via`` lines::

        10.0.0.0/24, ubest/mbest: 1/0, attached
            *via 10.0.0.1, Vlan1, [0/0], 2d03h, direct
        10.1.0.0/16, ubest/mbest: 1/0
            *via 10.0.0.254, [1/0], 01:30:00, static
    """
    results: list[RouteEntry] = []
    current_dest: str | None = None

    for line in output.splitlines():
        # Destination header: "10.0.0.0/24, ubest/mbest: 1/0, attached"
        m = _ROUTE_NXOS_DEST.match(line)
        if m:
            current_dest = m.group(1)
            continue

        # Via line: "  *via 10.0.0.1, Vlan1, [0/0], 2d03h, direct"
        if current_dest is None:
            continue
        m = _ROUTE_NXOS_VIA.match(line)
        if not m:
            continue
        next_hop = m.group(1)
        rest = m.group(2)

        # Parse comma-separated fields after the next-hop IP
        intf: str | None = None
        metric: str | None = None
        rtype_kw = ""
        for field in (f.strip() for f in rest.split(",") if f.strip()):
            # [AD/metric] bracket
            bm = _ROUTE_NXOS_METRIC.match(field)
            if bm:
                metric = bm.group(1)
                continue
            # Age tokens like "2d03h", "01:30:00", "00:05:30"
            if _ROUTE_NXOS_AGE.match(field):
                continue
            # Interface names start with a letter and contain letters/digits/slashes
            if _ROUTE_NXOS_INTF_SLASH.match(field) and "/" in field:
                intf = field
                continue
            # Known interface prefixes without slash (e.g. Vlan1, loopback0)
            if _ROUTE_NXOS_INTF_PREFIX.match(field):
                intf = field
                continue
            # Route type keyword (first match wins — ignore suffixes like "intra")
            if not rtype_kw and _ROUTE_NXOS_RTYPE.match(field):
                rtype_kw = field

        # Strip OSPF process name like "ospf-1" to "ospf"
        rtype_base = rtype_kw.split("-")[0].lower() if rtype_kw else ""
        route_type = _NXOS_ROUTE_TYPE_MAP.get(rtype_base, rtype_base or None)
        proto = _NXOS_PROTO_CODE.get(rtype_base)
        results.append(
            RouteEntry(
                protocol=proto,
                route_type=route_type,
                destination=current_dest,
                next_hop=next_hop,
                interface=intf,
                metric=metric,
            )
        )

    return results


def _parse_ip_route_cbs(output: str) -> list[RouteEntry]:
    """Parse CBS/C1200 ``show ip route`` output.

    CBS format uses a simplified table::

        S   0.0.0.0/0        via 192.168.1.1                  active
        C   192.168.1.0/24        directly connected, vlan 1   active
    """
    results: list[RouteEntry] = []

    for line in output.splitlines():
        # CBS connected: "C   192.168.1.0/24   directly connected, vlan 1   active"
        m = _ROUTE_CBS_CONNECTED.match(line)
        if m:
            code = m.group(1)
            vlan_num = m.group(3)
            results.append(
                RouteEntry(
                    protocol=code,
                    route_type=_ROUTE_TYPE_MAP.get(code, code.lower()),
                    destination=m.group(2),
                    next_hop=None,
                    interface=f"vlan {vlan_num}",
                    metric=None,
                )
            )
            continue

        # CBS via route: "S   0.0.0.0/0   via 192.168.1.1   active"
        m = _ROUTE_CBS_VIA.match(line)
        if m:
            code = m.group(1)
            results.append(
                RouteEntry(
                    protocol=code,
                    route_type=_ROUTE_TYPE_MAP.get(code, code.lower()),
                    destination=m.group(2),
                    next_hop=m.group(3),
                    interface=None,
                    metric=None,
                )
            )
            continue

    return results


# ---------------------------------------------------------------------------
# Show etherchannel summary
# ---------------------------------------------------------------------------

_MEMBER_FLAG_DESC: dict[str, str] = {
    "P": "bundled",
    "D": "down",
    "I": "stand-alone",
    "s": "suspended",
    "H": "hot-standby",
    "w": "waiting",
    "M": "min-links not met",
    "m": "min-links not met",
    "u": "unsuitable",
    "f": "alloc failed",
    "d": "default port",
    "p": "up (delay-lacp)",
    "r": "module-removed",
    "b": "BFD wait",
}


def parse_etherchannel_summary(output: str) -> list[EtherChannelInfo]:
    """Parse ``show etherchannel summary`` for IOS-XE and NX-OS."""
    results: list[EtherChannelInfo] = []

    in_data = False
    for line in output.splitlines():
        if _EC_SEPARATOR.match(line):
            in_data = True
            continue
        if not in_data or not line.strip():
            continue

        m = _EC_CHANNEL_ID.match(line)
        if not m:
            continue

        channel_id = m.group(1)

        po_match = _EC_PO_MATCH.search(line)
        if not po_match:
            continue
        port_channel = po_match.group(1)
        po_flags = po_match.group(2)

        layer = None
        status = ""
        for ch in po_flags:
            if ch in ("S", "R"):
                layer = ch
            elif ch in ("U", "D", "N"):
                status = ch

        protocol = None
        proto_match = _EC_PROTOCOL.search(line)
        if proto_match:
            val = proto_match.group(1)
            if val.upper() != "NONE":
                protocol = val

        members: list[ChannelMember] = []
        for member_match in _EC_MEMBER.finditer(line):
            intf_name = member_match.group(1)
            if intf_name.startswith("Po"):
                continue
            flag = member_match.group(2)
            members.append(
                ChannelMember(
                    interface=intf_name,
                    status=flag,
                    status_desc=_MEMBER_FLAG_DESC.get(flag),
                )
            )

        results.append(
            EtherChannelInfo(
                channel_id=channel_id,
                port_channel=port_channel,
                layer="Layer2" if layer == "S" else "Layer3" if layer == "R" else None,
                status="up" if status == "U" else "down" if status == "D" else status,
                protocol=protocol,
                members=members,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Show nve peers (VXLAN)
# ---------------------------------------------------------------------------


def parse_nve_peers(output: str) -> list[NVEPeer]:
    """Parse ``show nve peers`` output.

    NX-OS::

        Interface Peer-IP          State LearnType Uptime   Router-Mac
        --------- ---------------  ----- --------- -------- -----------------
        nve1      10.1.1.2         Up    CP        1d02h    5254.0012.3456
        nve1      10.1.1.3         Up    CP        1d02h    5254.0012.3457
        nve1      10.1.1.4         Down  CP        00:00:00 n/a
    """
    results: list[NVEPeer] = []
    in_data = False

    for line in output.splitlines():
        if _NVE_PEERS_HEADER.match(line):
            in_data = True
            continue
        if _NVE_BLANK_OR_DASH.match(line):
            continue
        if not in_data or not line.strip():
            continue
        # Data rows start with nve
        parts = line.split()
        if len(parts) < 3 or not parts[0].lower().startswith("nve"):
            continue
        results.append(
            NVEPeer(
                interface=parts[0],
                peer_ip=parts[1],
                state=parts[2],
                learn_type=parts[3] if len(parts) > 3 else None,
                uptime=parts[4] if len(parts) > 4 else None,
                router_mac=parts[5] if len(parts) > 5 else None,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Show nve vni (VXLAN)
# ---------------------------------------------------------------------------


def parse_nve_vni(output: str) -> list[VNIMapping]:
    """Parse ``show nve vni`` output.

    NX-OS::

        Codes: CP - Control Plane        DP - Data Plane
               UC - Unconfigured         SA - Suppress ARP

        Interface VNI      Multicast-group   State Mode Type  [BD/VRF]      Flags
        --------- -------- ----------------- ----- ---- ----- ------------- -----
        nve1      50001    UnicastBGP        Up    CP   L2 [1001]
        nve1      50002    UnicastBGP        Up    CP   L2 [1002]
        nve1      50100    n/a               Up    CP   L3 [Tenant-VRF]
    """
    results: list[VNIMapping] = []
    in_data = False

    for line in output.splitlines():
        if _NVE_VNI_HEADER.match(line):
            in_data = True
            continue
        if _NVE_BLANK_OR_DASH.match(line):
            continue
        if not in_data or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 3 or not parts[0].lower().startswith("nve"):
            continue

        # Type field may contain space: "L2 [1001]" or "L3 [Tenant-VRF]"
        # Find VNI type and BD/VRF from the tail
        vni_type = None
        bd_vrf = None
        type_match = _NVE_VNI_TYPE.search(line)
        if type_match:
            vni_type = f"{type_match.group(1)} [{type_match.group(2)}]"
            bd_vrf = type_match.group(2)

        results.append(
            VNIMapping(
                interface=parts[0],
                vni=parts[1],
                multicast_group=parts[2] if len(parts) > 2 else None,
                state=parts[3] if len(parts) > 3 else None,
                mode=parts[4] if len(parts) > 4 else None,
                vni_type=vni_type,
                bd_vrf=bd_vrf,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Show bgp l2vpn evpn summary (VXLAN)
# ---------------------------------------------------------------------------


def parse_bgp_evpn_summary(output: str) -> list[EVPNNeighbor]:
    """Parse ``show bgp l2vpn evpn summary`` output.

    NX-OS::

        BGP summary information for VRF default, address family L2VPN EVPN
        BGP router identifier 10.1.1.1, local AS number 65001
        ...
        Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
        10.1.1.2        4 65001   12345   12300      100    0    0 1d02h    100
        10.1.1.3        4 65001    9876    9800      100    0    0 2d05h    85
    """
    results: list[EVPNNeighbor] = []
    in_data = False

    for line in output.splitlines():
        if _BGP_EVPN_HEADER.match(line):
            in_data = True
            continue
        if not in_data or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        # Data rows start with an IP address
        if not _BGP_EVPN_IP.match(parts[0]):
            continue
        results.append(
            EVPNNeighbor(
                neighbor=parts[0],
                version=parts[1] if len(parts) > 1 else None,
                asn=parts[2] if len(parts) > 2 else None,
                msg_rcvd=parts[3] if len(parts) > 3 else None,
                msg_sent=parts[4] if len(parts) > 4 else None,
                up_down=parts[8] if len(parts) > 8 else None,
                state_pfx_rcv=parts[9] if len(parts) > 9 else None,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Show spanning-tree
# ---------------------------------------------------------------------------


def parse_spanning_tree(output: str) -> list[STPVlanInfo]:
    """Parse ``show spanning-tree`` output.

    Handles IOS-XE and NX-OS.  Output is split on ``VLAN\\d+`` boundaries;
    each block contains Root ID / Bridge ID sections and an interface table.
    """
    if not output or not output.strip():
        return []

    results: list[STPVlanInfo] = []

    # Split on VLAN boundaries.  Each section starts with "VLAN0001" or "VLAN0010" etc.
    vlan_blocks = _STP_VLAN_SPLIT.split(output)

    for block in vlan_blocks:
        block = block.strip()
        if not block:
            continue

        # Extract VLAN ID from the header line
        vlan_match = _STP_VLAN_MATCH.match(block)
        if not vlan_match:
            continue
        vlan_id = str(int(vlan_match.group(1)))  # strip leading zeros: "0001" -> "1"

        # Protocol: "Spanning tree enabled protocol rstp"
        protocol = _extract(_STP_PROTOCOL, block)

        # Detect if this bridge is root
        is_root = bool(_STP_IS_ROOT.search(block))

        # Root ID section
        root_priority = _extract(_STP_ROOT_PRIORITY, block)
        root_address = _extract(_STP_ROOT_ADDRESS, block)
        root_cost = _extract(_STP_ROOT_COST, block) if not is_root else "0"

        # Bridge ID section
        bridge_priority = _extract(_STP_BRIDGE_PRIORITY, block)
        bridge_address = _extract(_STP_BRIDGE_ADDRESS, block)

        # Parse interface table
        ports: list[STPPortInfo] = []
        # Find the header line: "Interface  Role Sts  Cost  Prio.Nbr Type"
        # or NX-OS: "Interface  Role Sts  Cost  Guard  Type"
        intf_header = _STP_INTF_HEADER.search(block)
        if intf_header:
            table_start = intf_header.end()
            table_lines = block[table_start:].splitlines()
            for line in table_lines:
                line = line.rstrip()
                if not line or _STP_DASH_LINE.match(line):
                    continue
                # Stop at next section or blank
                if _STP_BLANK_LINE.match(line):
                    break
                # Parse fixed-width columns.  Interface name starts at col 0,
                # Role is 4 chars (Root/Desg/Altn/Back), Sts is 3 chars (FWD/BLK/LRN/LIS/DIS)
                # Use regex to be flexible with spacing:
                # "Gi1/0/1             Root FWD 4         128.1    P2p"
                m = _STP_PORT_FULL.match(line)
                if m:
                    ports.append(
                        STPPortInfo(
                            interface=normalize_interface_name(m.group(1)),
                            role=m.group(2),
                            state=m.group(3),
                            cost=m.group(4),
                            port_priority=m.group(5),
                            link_type=m.group(6).strip(),
                        )
                    )
                    continue
                # Fallback: minimal match (fewer columns, e.g. missing type)
                m2 = _STP_PORT_MINIMAL.match(line)
                if m2:
                    ports.append(
                        STPPortInfo(
                            interface=normalize_interface_name(m2.group(1)),
                            role=m2.group(2),
                            state=m2.group(3),
                            cost=m2.group(4),
                        )
                    )

        results.append(
            STPVlanInfo(
                vlan_id=vlan_id,
                protocol=protocol,
                root_priority=root_priority,
                root_address=root_address,
                root_cost=root_cost,
                is_root=is_root,
                bridge_priority=bridge_priority,
                bridge_address=bridge_address,
                ports=ports,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Show inventory
# ---------------------------------------------------------------------------


def parse_inventory(output: str) -> list[InventoryItem]:
    """Parse ``show inventory`` output.

    IOS-XE::

        NAME: "Chassis", DESCR: "Cisco Catalyst 3850-48P Switch"
        PID: WS-C3850-48P      , VID: V02  , SN: FCW1234A0BC

        NAME: "Switch 1 - Power Supply 1", DESCR: "Switch 1 - Power Supply 1"
        PID: PWR-C1-1100WAC    , VID: V02  , SN: LIT1234A0BC
    """
    items: list[InventoryItem] = []
    current: InventoryItem | None = None

    for line in output.splitlines():
        name_match = _INV_NAME_DESCR.search(line)
        if name_match:
            if current is not None:
                items.append(current)
            current = InventoryItem(name=name_match.group(1), description=name_match.group(2))
            continue

        if current is not None:
            pid_m = _INV_PID.search(line)
            vid_m = _INV_VID.search(line)
            sn_m = _INV_SN.search(line)
            if pid_m:
                current.pid = pid_m.group(1).rstrip(",")
            if vid_m:
                current.vid = vid_m.group(1).rstrip(",")
            if sn_m:
                current.serial = sn_m.group(1).rstrip(",")

    if current is not None:
        items.append(current)

    return items


# ---------------------------------------------------------------------------
# Show interfaces trunk
# ---------------------------------------------------------------------------


def parse_interfaces_trunk(output: str) -> dict[str, TrunkInfo]:
    """Parse ``show interfaces trunk`` output into a per-port dict.

    Handles both IOS-XE and NX-OS output formats.

    IOS-XE emits four sections separated by blank lines::

        Port        Mode             Encapsulation  Status        Native vlan
        Gi1/0/1     on               802.1q         trunking      1

        Port        Vlans allowed on trunk
        Gi1/0/1     1-4094

        Port        Vlans allowed and active in management domain
        Gi1/0/1     1,10,20,30

        Port        Vlans in spanning tree forwarding state and not pruned
        Gi1/0/1     1,10,20

    NX-OS uses a different layout with separator lines and different headers::

        Port          Native Vlan  Status        Port Channel
        Eth1/1        1            trunking      --

        Port          Vlans Allowed on Trunk
        Eth1/1        1-4094

        Port          STP Forwarding
        Eth1/1        1,100
    """
    trunks: dict[str, TrunkInfo] = {}
    section: str | None = None

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Skip separator lines (dash rows)
        if _TRUNK_SEPARATOR.match(stripped):
            continue

        # Section header detection — IOS-XE first (Mode present), then NX-OS
        if line.startswith("Port") and "Mode" in line and "Native" in line:
            section = "status"
            continue
        # NX-OS status header: "Port  Native Vlan  Status  Port Channel"
        if line.startswith("Port") and "Native Vlan" in line and "Mode" not in line:
            section = "nxos_status"
            continue
        # IOS-XE allowed vlans (case-sensitive lower-case 'allowed')
        if line.startswith("Port") and "Vlans allowed on trunk" in line:
            section = "allowed"
            continue
        # NX-OS allowed vlans (title-case 'Allowed')
        if line.startswith("Port") and "Vlans Allowed on Trunk" in line:
            section = "allowed"
            continue
        if line.startswith("Port") and "Vlans allowed and active" in line:
            section = "active"
            continue
        if line.startswith("Port") and "Vlans in spanning tree" in line:
            section = "forwarding"
            continue
        # NX-OS STP forwarding section
        if line.startswith("Port") and "STP Forwarding" in line:
            section = "forwarding"
            continue
        # NX-OS error-disabled section — skip
        if line.startswith("Port") and "Err-disabled" in line:
            section = None
            continue
        # Other "Port ..." header lines we don't recognise — skip
        if line.startswith("Port") and len(stripped.split()) > 1:
            section = None
            continue

        parts = stripped.split()
        if not parts or not _TRUNK_ALPHA.match(parts[0]):
            continue

        port = parts[0]
        if port not in trunks:
            trunks[port] = TrunkInfo()

        if section == "status" and len(parts) >= 5:
            trunks[port].mode = parts[1]
            trunks[port].encapsulation = parts[2]
            trunks[port].status = parts[3]
            trunks[port].native_vlan = parts[4]
        elif section == "nxos_status" and len(parts) >= 3:
            # NX-OS: port  native_vlan  status  [port_channel]
            trunks[port].native_vlan = parts[1]
            trunks[port].status = parts[2]
        elif section == "allowed" and len(parts) >= 2:
            trunks[port].allowed_vlans = " ".join(parts[1:])
        elif section == "active" and len(parts) >= 2:
            trunks[port].active_vlans = " ".join(parts[1:])
        elif section == "forwarding" and len(parts) >= 2:
            trunks[port].forwarding_vlans = " ".join(parts[1:])

    return trunks


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _extract(pattern: re.Pattern[str] | str, text: str, flags: int = 0) -> str | None:
    if isinstance(pattern, re.Pattern):
        m = pattern.search(text)
    else:
        m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None
