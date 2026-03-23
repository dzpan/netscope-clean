"""Cisco IOS-XE / NX-OS / CBS vendor plugin.

Wraps the existing pure-function parsers in ``backend.parsers`` behind the
``VendorPlugin`` protocol.  No parser logic is duplicated — this is purely a
dispatch layer.
"""

from __future__ import annotations

import re
from typing import Any

from backend.models import (
    InterfaceInfo,
    NeighborRecord,
    VersionInfo,
)
from backend.parsers import (
    build_interface_ip_map,
    parse_arp_table,
    parse_bgp_evpn_summary,
    parse_cdp_neighbors,
    parse_etherchannel_summary,
    parse_interfaces_status,
    parse_interfaces_trunk,
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


class CiscoPlugin:
    """Vendor plugin for Cisco IOS-XE, NX-OS, and CBS/C1200 platforms."""

    vendor_id: str = "cisco"
    display_name: str = "Cisco IOS-XE / NX-OS / CBS"

    # --- detection -----------------------------------------------------------

    _DETECT_PATTERNS = [
        re.compile(r"Cisco\s+IOS", re.IGNORECASE),
        re.compile(r"IOS-XE", re.IGNORECASE),
        re.compile(r"NX-OS", re.IGNORECASE),
        re.compile(r"Cisco\s+Nexus", re.IGNORECASE),
        re.compile(r"CBS\d+|C1[12]\d{2}", re.IGNORECASE),
        re.compile(r"Catalyst", re.IGNORECASE),
        re.compile(r"cisco", re.IGNORECASE),  # broad fallback
    ]

    def detect(self, version_output: str) -> bool:
        return any(p.search(version_output) for p in self._DETECT_PATTERNS)

    # --- version -------------------------------------------------------------

    def parse_version(self, output: str) -> VersionInfo:
        return parse_show_version(output)

    # --- neighbors -----------------------------------------------------------

    def parse_neighbors(
        self,
        cdp_output: str | None,
        lldp_output: str | None,
        platform: str | None = None,
    ) -> list[NeighborRecord]:
        records: list[NeighborRecord] = []
        if cdp_output:
            records.extend(parse_cdp_neighbors(cdp_output))
        if lldp_output:
            records.extend(parse_lldp_neighbors(lldp_output, platform=platform))
        return records

    # --- command mapping -----------------------------------------------------

    _GROUP_COMMANDS: dict[str, list[str]] = {
        "interfaces": ["show interfaces status", "show ip interface brief"],
        "vlans": ["show vlan brief"],
        "arp": ["show ip arp"],
        "mac": ["show mac address-table"],
        "routes": ["show ip route"],
        "etherchannel": ["show etherchannel summary"],
        "spanning_tree": ["show spanning-tree"],
        "trunks": ["show interfaces trunk"],
        "vxlan": ["show nve peers", "show nve vni", "show bgp l2vpn evpn summary"],
    }

    def get_commands(self, groups: frozenset[str]) -> dict[str, list[str]]:
        return {g: list(self._GROUP_COMMANDS[g]) for g in groups if g in self._GROUP_COMMANDS}

    # --- group parsing -------------------------------------------------------

    def parse_group(self, group: str, outputs: dict[str, str]) -> dict[str, Any]:
        """Dispatch to the appropriate existing parser functions."""
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
        if group == "etherchannel":
            return self._parse_etherchannel(outputs)
        if group == "spanning_tree":
            return self._parse_stp(outputs)
        if group == "trunks":
            return self._parse_trunks(outputs)
        if group == "vxlan":
            return self._parse_vxlan(outputs)
        return {}

    # --- private group parsers -----------------------------------------------

    @staticmethod
    def _parse_interfaces(outputs: dict[str, str]) -> dict[str, Any]:
        interfaces: list[InterfaceInfo] = []
        status_out = outputs.get("show interfaces status", "")
        brief_out = outputs.get("show ip interface brief", "")

        if status_out:
            interfaces = parse_interfaces_status(status_out)
        if not interfaces and brief_out:
            interfaces = parse_ip_interface_brief(brief_out)

        # Merge IP addresses
        if brief_out:
            ip_map = build_interface_ip_map(brief_out)
            if ip_map:
                for intf in interfaces:
                    intf_ip = ip_map.get(intf.name)
                    if intf_ip:
                        intf.ip_address = intf_ip

        return {"interfaces": interfaces}

    @staticmethod
    def _parse_vlans(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show vlan brief", "") or outputs.get("show vlan", "")
        return {"vlans": parse_vlan_brief(out) if out else []}

    @staticmethod
    def _parse_arp(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show ip arp", "") or outputs.get("show arp", "")
        return {"arp_table": parse_arp_table(out) if out else []}

    @staticmethod
    def _parse_mac(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show mac address-table", "")
        return {"mac_table": parse_mac_address_table(out) if out else []}

    @staticmethod
    def _parse_routes(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show ip route", "")
        return {"route_table": parse_ip_route(out) if out else []}

    @staticmethod
    def _parse_etherchannel(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show etherchannel summary", "")
        return {"etherchannels": parse_etherchannel_summary(out) if out else []}

    @staticmethod
    def _parse_stp(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show spanning-tree", "")
        return {"stp_info": parse_spanning_tree(out) if out else []}

    @staticmethod
    def _parse_trunks(outputs: dict[str, str]) -> dict[str, Any]:
        out = outputs.get("show interfaces trunk", "")
        return {"trunk_info": parse_interfaces_trunk(out) if out else {}}

    @staticmethod
    def _parse_vxlan(outputs: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        nve_out = outputs.get("show nve peers", "")
        vni_out = outputs.get("show nve vni", "")
        evpn_out = outputs.get("show bgp l2vpn evpn summary", "")
        result["nve_peers"] = parse_nve_peers(nve_out) if nve_out else []
        result["vni_mappings"] = parse_nve_vni(vni_out) if vni_out else []
        result["evpn_neighbors"] = parse_bgp_evpn_summary(evpn_out) if evpn_out else []
        return result

    # --- terminal setup ------------------------------------------------------

    async def on_open(self, conn: Any) -> None:
        """Cisco-specific terminal setup: terminal length 0 or terminal datadump."""
        await conn.acquire_priv(desired_priv=conn.default_desired_privilege_level)

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
                pass

    # --- driver config -------------------------------------------------------

    def get_driver_kwargs(self) -> dict[str, Any]:
        """Cisco uses AsyncIOSXEDriver — no extra kwargs needed."""
        return {}

    # --- neighbor commands ---------------------------------------------------

    def neighbor_commands(self) -> dict[str, str]:
        return {
            "cdp": "show cdp neighbors detail",
            "lldp": "show lldp neighbors detail",
        }

    def not_enabled_markers(self) -> dict[str, list[str]]:
        return {
            "cdp": ["CDP is not enabled"],
            "lldp": ["LLDP is not enabled"],
        }
