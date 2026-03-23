"""Arista EOS vendor plugin.

Parses Arista EOS CLI output for discovery and data collection.  EOS output
is similar to Cisco IOS-XE in many areas but has notable differences in
``show version``, ``show vlan``, and LLDP output formatting.
"""

from __future__ import annotations

import re
from typing import Any

from backend.models import (
    ArpEntry,
    InterfaceInfo,
    MacTableEntry,
    NeighborRecord,
    RouteEntry,
    VersionInfo,
    VlanInfo,
)
from backend.normalizer import normalize_interface_name
from backend.parsers import parse_lldp_neighbors


class AristaPlugin:
    """Vendor plugin for Arista EOS platforms."""

    vendor_id: str = "arista"
    display_name: str = "Arista EOS"

    # --- detection -----------------------------------------------------------

    _DETECT_PATTERNS = [
        re.compile(r"Arista", re.IGNORECASE),
        re.compile(r"vEOS", re.IGNORECASE),
        re.compile(r"EOS", re.IGNORECASE),
    ]

    def detect(self, version_output: str) -> bool:
        return any(p.search(version_output) for p in self._DETECT_PATTERNS)

    # --- version -------------------------------------------------------------

    def parse_version(self, output: str) -> VersionInfo:
        """Parse Arista EOS ``show version`` output.

        Example::

            Arista vEOS-lab
            Hardware version: 04.00
            Serial number: SN-ARISTA-01
            Hardware MAC address: 5001.0001.0000
            System MAC address: 5001.0001.0000
            Software image version: 4.28.3M
            ...
            Uptime: 2 days, 3 hours, 15 minutes
            ...
            Hostname: leaf-01
        """
        hostname = _extract(r"[Hh]ostname:\s*(\S+)", output)
        # Arista may also have hostname in the prompt before the output
        if not hostname:
            hostname = _extract(r"^(\S+)\s*>", output) or _extract(r"^(\S+)#", output)

        platform = _extract(r"^(Arista\s+\S+)", output, re.MULTILINE)
        if not platform:
            platform = _extract(r"(Arista\s+DCS-\S+)", output)

        serial = _extract(r"Serial\s+number:\s*(\S+)", output, re.IGNORECASE)
        os_version = _extract(r"Software\s+image\s+version:\s*(\S+)", output, re.IGNORECASE)
        if not os_version:
            os_version = _extract(r"EOS\s+version:\s*(\S+)", output, re.IGNORECASE)

        uptime = _extract(r"Uptime:\s*(.+)", output)
        if uptime:
            uptime = uptime.strip()

        base_mac = _extract(r"System\s+MAC\s+address:\s*(\S+)", output, re.IGNORECASE)
        if not base_mac:
            base_mac = _extract(r"Hardware\s+MAC\s+address:\s*(\S+)", output, re.IGNORECASE)

        return VersionInfo(
            hostname=hostname,
            platform=platform,
            serial=serial,
            os_version=os_version,
            uptime=uptime,
            base_mac=base_mac,
        )

    # --- neighbors -----------------------------------------------------------

    def parse_neighbors(
        self,
        cdp_output: str | None,
        lldp_output: str | None,
        platform: str | None = None,
    ) -> list[NeighborRecord]:
        """Arista uses LLDP primarily.  CDP is optional (disabled by default)."""
        records: list[NeighborRecord] = []
        if lldp_output:
            records.extend(parse_lldp_neighbors(lldp_output, platform="cisco"))
        if cdp_output:
            records.extend(_parse_arista_cdp(cdp_output))
        return records

    # --- command mapping -----------------------------------------------------

    _GROUP_COMMANDS: dict[str, list[str]] = {
        "interfaces": ["show interfaces status", "show ip interface brief"],
        "vlans": ["show vlan"],
        "arp": ["show ip arp"],
        "mac": ["show mac address-table"],
        "routes": ["show ip route"],
    }

    def get_commands(self, groups: frozenset[str]) -> dict[str, list[str]]:
        return {g: list(self._GROUP_COMMANDS[g]) for g in groups if g in self._GROUP_COMMANDS}

    # --- group parsing -------------------------------------------------------

    def parse_group(self, group: str, outputs: dict[str, str]) -> dict[str, Any]:
        if group == "interfaces":
            return self._parse_interfaces(outputs)
        if group == "vlans":
            return self._parse_vlans(outputs)
        if group == "arp":
            return self._parse_arp(outputs)
        if group == "mac":
            return self._parse_mac(outputs)
        if group == "routes":
            return self._parse_routes(outputs)
        return {}

    # --- private group parsers -----------------------------------------------

    @staticmethod
    def _parse_interfaces(outputs: dict[str, str]) -> dict[str, Any]:
        interfaces: list[InterfaceInfo] = []
        status_out = outputs.get("show interfaces status", "")
        brief_out = outputs.get("show ip interface brief", "")

        if status_out:
            interfaces = _parse_eos_interfaces_status(status_out)
        if not interfaces and brief_out:
            interfaces = _parse_eos_ip_interface_brief(brief_out)

        # Merge IP addresses from brief output
        if brief_out and interfaces:
            ip_map = _build_eos_ip_map(brief_out)
            for intf in interfaces:
                ip = ip_map.get(intf.name)
                if ip:
                    intf.ip_address = ip

        return {"interfaces": interfaces}

    @staticmethod
    def _parse_vlans(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show vlan", "")
        return {"vlans": _parse_eos_vlan(out) if out else []}

    @staticmethod
    def _parse_arp(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show ip arp", "")
        return {"arp_table": _parse_eos_arp(out) if out else []}

    @staticmethod
    def _parse_mac(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show mac address-table", "")
        return {"mac_table": _parse_eos_mac(out) if out else []}

    @staticmethod
    def _parse_routes(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show ip route", "")
        return {"route_table": _parse_eos_routes(out) if out else []}

    # --- terminal setup ------------------------------------------------------

    async def on_open(self, conn: Any) -> None:
        """EOS terminal setup: ``terminal length 0`` (same as IOS-XE)."""
        await conn.acquire_priv(desired_priv=conn.default_desired_privilege_level)
        try:
            await conn.send_command("terminal length 0")
        except Exception:
            pass

    # --- driver config -------------------------------------------------------

    def get_driver_kwargs(self) -> dict[str, Any]:
        """Arista EOS uses the same Scrapli IOSXEDriver with asyncssh."""
        return {}

    # --- neighbor commands ---------------------------------------------------

    def neighbor_commands(self) -> dict[str, str]:
        return {
            "lldp": "show lldp neighbors detail",
        }

    def not_enabled_markers(self) -> dict[str, list[str]]:
        return {
            "lldp": ["LLDP is not enabled"],
        }


# ---------------------------------------------------------------------------
# Arista EOS parsers — standalone functions
# ---------------------------------------------------------------------------

_IPV4 = r"\d{1,3}(?:\.\d{1,3}){3}"


def _extract(pattern: str, text: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _parse_arista_cdp(output: str) -> list[NeighborRecord]:
    """Parse Arista ``show cdp neighbors detail`` (rare — CDP off by default).

    Format is nearly identical to Cisco IOS-XE CDP output.
    """
    from backend.parsers import parse_cdp_neighbors

    return parse_cdp_neighbors(output)


def _parse_eos_interfaces_status(output: str) -> list[InterfaceInfo]:
    """Parse ``show interfaces status`` on EOS using column-position detection.

    Example::

        Port       Name       Status       Vlan     Duplex  Speed  Type
        Et1                   connected    1        full    1G     10GBASE-T
        Et2        uplink     connected    trunk    full    10G    10GBASE-T
        Ma1                   connected    routed   full    1G     10/100/1000
    """
    interfaces: list[InterfaceInfo] = []
    col_starts: dict[str, int] = {}
    header_line = ""

    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue

        if re.match(r"Port\s+Name\s+Status", line, re.IGNORECASE):
            header_line = line
            # Detect column start positions from header
            for col_name in ["Port", "Name", "Status", "Vlan", "Duplex", "Speed", "Type"]:
                idx = header_line.find(col_name)
                if idx >= 0:
                    col_starts[col_name.lower()] = idx
            continue

        if not col_starts:
            continue

        # Extract fields by column position
        def _col(name: str, next_name: str | None = None) -> str:
            start = col_starts.get(name, 0)
            if next_name and next_name in col_starts:
                end = col_starts.get(next_name, len(line))
            else:
                end = len(line)
            return line[start:end].strip() if start < len(line) else ""

        port = _col("port", "name")
        name = _col("name", "status")
        status = _col("status", "vlan")
        vlan = _col("vlan", "duplex")
        duplex = _col("duplex", "speed")
        speed = _col("speed", "type")

        if not port or not re.match(r"[A-Za-z]", port):
            continue

        interfaces.append(
            InterfaceInfo(
                name=normalize_interface_name(port),
                status=status.lower() if status else None,
                vlan=vlan if vlan and vlan.lower() not in ("trunk", "routed") else None,
                speed=speed or None,
                duplex=duplex.lower() if duplex else None,
                description=name or None,
            )
        )

    return interfaces


def _parse_eos_ip_interface_brief(output: str) -> list[InterfaceInfo]:
    """Parse ``show ip interface brief`` on EOS.

    Example::

        Interface              IP Address         Status       Protocol       MTU
        Ethernet1              10.0.0.1/24        up           up             1500
        Loopback0              1.1.1.1/32         up           up             65535
        Management1            192.168.1.10/24    up           up             1500
    """
    interfaces: list[InterfaceInfo] = []
    header_seen = False

    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if re.match(r"Interface\s+IP\s+Address", line, re.IGNORECASE):
            header_seen = True
            continue
        if not header_seen:
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        name = normalize_interface_name(parts[0])
        ip_raw = parts[1]
        status = parts[2].lower() if len(parts) > 2 else None

        # Strip CIDR mask from IP
        ip_candidate = ip_raw.split("/")[0] if "/" in ip_raw else ip_raw
        ip_addr: str | None = ip_candidate if re.match(_IPV4, ip_candidate) else None

        interfaces.append(
            InterfaceInfo(
                name=name,
                status=status,
                ip_address=ip_addr,
            )
        )

    return interfaces


def _build_eos_ip_map(output: str) -> dict[str, str]:
    """Build interface → IP map from ``show ip interface brief``."""
    ip_map: dict[str, str] = {}
    header_seen = False

    for line in output.splitlines():
        if re.match(r"Interface\s+IP\s+Address", line, re.IGNORECASE):
            header_seen = True
            continue
        if not header_seen:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        name = normalize_interface_name(parts[0])
        ip_raw = parts[1].split("/")[0]
        if re.match(_IPV4, ip_raw):
            ip_map[name] = ip_raw

    return ip_map


def _parse_eos_vlan(output: str) -> list[VlanInfo]:
    """Parse ``show vlan`` on EOS.

    Example::

        VLAN  Name                             Status    Ports
        ----- -------------------------------- --------- -----------------------
        1     default                          active    Et1, Et2
        10    MGMT                             active    Et3
        100   Production                       active
    """
    vlans: list[VlanInfo] = []
    header_seen = False

    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if re.match(r"VLAN\s+Name", line, re.IGNORECASE):
            header_seen = True
            continue
        if re.match(r"---", line):
            continue
        if not header_seen:
            continue

        m = re.match(r"(\d+)\s+(\S+(?:\s+\S+)*?)\s+(active|suspend|act/unsup)", line, re.IGNORECASE)
        if m:
            vlans.append(
                VlanInfo(
                    vlan_id=m.group(1),
                    name=m.group(2).strip(),
                    status=m.group(3).lower(),
                )
            )

    return vlans


def _parse_eos_arp(output: str) -> list[ArpEntry]:
    """Parse ``show ip arp`` on EOS.

    Example::

        Address         Age (sec)  Hardware Addr   Interface
        10.0.0.1        0:00:05    5001.0001.0001  Ethernet1, Vlan10
        10.0.0.2        0:03:22    5001.0002.0001  Ethernet2
    """
    entries: list[ArpEntry] = []
    header_seen = False

    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if re.match(r"Address\s+Age", line, re.IGNORECASE):
            header_seen = True
            continue
        if not header_seen:
            continue

        m = re.match(
            rf"({_IPV4})\s+"
            r"[\d:]+\s+"  # Age
            r"([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"  # MAC
            r"(\S+)",  # Interface
            line,
        )
        if m:
            entries.append(
                ArpEntry(
                    ip_address=m.group(1),
                    mac_address=m.group(2).lower(),
                    interface=normalize_interface_name(m.group(3).rstrip(",")),
                    entry_type="dynamic",
                )
            )

    return entries


def _parse_eos_mac(output: str) -> list[MacTableEntry]:
    """Parse ``show mac address-table`` on EOS.

    Example::

        Mac Address Table
        ------------------------------------------------------------------
              Vlan    Mac Address       Type        Ports
              ----    -----------       ----        -----
                 1    5001.0001.0001    DYNAMIC     Et1
                10    5001.0002.0001    DYNAMIC     Et2
    """
    entries: list[MacTableEntry] = []

    for line in output.splitlines():
        m = re.match(
            r"\s*(\d+)\s+"
            r"([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
            r"(\S+)\s+"  # Type
            r"(\S+)",  # Port
            line,
        )
        if m:
            entries.append(
                MacTableEntry(
                    vlan_id=m.group(1),
                    mac_address=m.group(2).lower(),
                    entry_type=m.group(3).lower(),
                    interface=normalize_interface_name(m.group(4)),
                )
            )

    return entries


_ROUTE_PROTOCOL_MAP: dict[str, str] = {
    "C": "connected",
    "L": "local",
    "S": "static",
    "O": "ospf",
    "B": "bgp",
}


def _parse_eos_routes(output: str) -> list[RouteEntry]:
    """Parse ``show ip route`` on EOS.

    EOS format is very similar to IOS-XE::

        VRF: default
         C        10.0.0.0/24 is directly connected, Ethernet1
         B        192.168.1.0/24 [200/0] via 10.0.0.2, Ethernet2
         S        0.0.0.0/0 [1/0] via 10.0.0.254
    """
    entries: list[RouteEntry] = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        # Match: "C  10.0.0.0/24 is directly connected, Ethernet1"
        m_connected = re.match(
            r"([CLSOBDR])\s+"
            rf"({_IPV4}/\d+)\s+is\s+directly\s+connected,\s*(\S+)",
            line,
        )
        if m_connected:
            code = m_connected.group(1)
            entries.append(
                RouteEntry(
                    protocol=code,
                    route_type=_ROUTE_PROTOCOL_MAP.get(code, code.lower()),
                    destination=m_connected.group(2),
                    interface=normalize_interface_name(m_connected.group(3)),
                )
            )
            continue

        # Match: "B  192.168.1.0/24 [200/0] via 10.0.0.2, Ethernet2"
        m_via = re.match(
            r"([CLSOBDR])\s+"
            rf"({_IPV4}/\d+)\s+"
            r"\[(\d+/\d+)\]\s+via\s+"
            rf"({_IPV4})"
            r"(?:,\s*(\S+))?",
            line,
        )
        if m_via:
            code = m_via.group(1)
            entries.append(
                RouteEntry(
                    protocol=code,
                    route_type=_ROUTE_PROTOCOL_MAP.get(code, code.lower()),
                    destination=m_via.group(2),
                    metric=m_via.group(3),
                    next_hop=m_via.group(4),
                    interface=normalize_interface_name(m_via.group(5)) if m_via.group(5) else None,
                )
            )

    return entries
