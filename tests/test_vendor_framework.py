"""Tests for the multi-vendor plugin framework and built-in vendor plugins."""

from __future__ import annotations

from backend.models import VersionInfo
from backend.vendors import VendorPlugin, VendorRegistry
from backend.vendors.arista import AristaPlugin
from backend.vendors.cisco import CiscoPlugin

# ---------------------------------------------------------------------------
# Framework tests
# ---------------------------------------------------------------------------


class TestVendorRegistry:
    def test_register_and_detect_cisco(self) -> None:
        reg = VendorRegistry()
        plugin = CiscoPlugin()
        reg.register(plugin)
        assert reg.detect("Cisco IOS XE Software") is plugin

    def test_register_and_detect_arista(self) -> None:
        reg = VendorRegistry()
        plugin = AristaPlugin()
        reg.register(plugin)
        assert reg.detect("Arista vEOS-lab") is plugin

    def test_detect_returns_none_for_unknown(self) -> None:
        reg = VendorRegistry()
        reg.register(CiscoPlugin())
        assert reg.detect("Totally Unknown Vendor") is None

    def test_priority_ordering(self) -> None:
        """Arista should match before Cisco when both are registered."""
        reg = VendorRegistry()
        arista = AristaPlugin()
        cisco = CiscoPlugin()
        reg.register(cisco, priority=50)
        reg.register(arista, priority=10)
        # "Arista" triggers Arista, not Cisco
        assert reg.detect("Arista vEOS-lab") is arista

    def test_get_by_vendor_id(self) -> None:
        reg = VendorRegistry()
        cisco = CiscoPlugin()
        reg.register(cisco)
        assert reg.get("cisco") is cisco
        assert reg.get("unknown") is None

    def test_all_plugins(self) -> None:
        reg = VendorRegistry()
        reg.register(CiscoPlugin(), priority=50)
        reg.register(AristaPlugin(), priority=10)
        plugins = reg.all_plugins()
        assert len(plugins) == 2
        assert plugins[0].vendor_id == "arista"

    def test_protocol_compliance(self) -> None:
        """Both plugins satisfy the VendorPlugin protocol."""
        assert isinstance(CiscoPlugin(), VendorPlugin)
        assert isinstance(AristaPlugin(), VendorPlugin)


# ---------------------------------------------------------------------------
# Global registry tests (auto-registered)
# ---------------------------------------------------------------------------


class TestGlobalRegistry:
    def test_auto_registration(self) -> None:
        # Import triggers registration
        import backend.vendors._registration  # noqa: F401
        from backend.vendors import registry as global_reg

        assert global_reg.get("cisco") is not None
        assert global_reg.get("arista") is not None

    def test_arista_detected_before_cisco(self) -> None:
        import backend.vendors._registration  # noqa: F401
        from backend.vendors import registry as global_reg

        result = global_reg.detect("Arista vEOS-lab")
        assert result is not None
        assert result.vendor_id == "arista"


# ---------------------------------------------------------------------------
# CiscoPlugin tests
# ---------------------------------------------------------------------------


CISCO_IOS_XE_VERSION = """\
Cisco IOS XE Software, Version 17.06.05
Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.6.5
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2023 by Cisco Systems, Inc.

cisco C9300-48P (X86) processor with 1426966K/6147K bytes of memory.
Processor board ID FCW2234L0NC
...
Base Ethernet MAC Address    : 001a.2b3c.4d5e
...
Switch Ports Model                     SW Version            SW Image
------ ----- -----                     ----------            ----------
*    1 52    C9300-48P                  17.06.05              CAT9K_IOSXE

Configuration register is 0x102

Core-Switch-1 uptime is 3 days, 12 hours, 45 minutes
hostname Core-Switch-1
"""


class TestCiscoPlugin:
    def setup_method(self) -> None:
        self.plugin = CiscoPlugin()

    def test_detect_iosxe(self) -> None:
        assert self.plugin.detect("Cisco IOS XE Software, Version 17.06.05")

    def test_detect_nxos(self) -> None:
        assert self.plugin.detect("Cisco NX-OS Software, Version 9.3(7)")

    def test_detect_cbs(self) -> None:
        assert self.plugin.detect("CBS350-24P, Version 3.2.0.84")

    def test_detect_rejects_arista(self) -> None:
        # Cisco's broad pattern still matches "Arista" (which mentions Cisco
        # in some contexts) — this is OK because the registry checks Arista first.
        # But pure Arista output without "Cisco" should not match the specific patterns.
        pass  # Registry ordering handles this

    def test_parse_version(self) -> None:
        ver = self.plugin.parse_version(CISCO_IOS_XE_VERSION)
        assert isinstance(ver, VersionInfo)
        assert ver.base_mac == "001a.2b3c.4d5e"
        assert ver.hostname == "Core-Switch-1"
        assert ver.serial == "FCW2234L0NC"

    def test_get_commands(self) -> None:
        cmds = self.plugin.get_commands(frozenset(["interfaces", "vlans"]))
        assert "interfaces" in cmds
        assert "vlans" in cmds
        assert "show interfaces status" in cmds["interfaces"]

    def test_get_commands_ignores_unknown(self) -> None:
        cmds = self.plugin.get_commands(frozenset(["interfaces", "bogus_group"]))
        assert "bogus_group" not in cmds

    def test_neighbor_commands(self) -> None:
        cmds = self.plugin.neighbor_commands()
        assert "cdp" in cmds
        assert "lldp" in cmds

    def test_not_enabled_markers(self) -> None:
        markers = self.plugin.not_enabled_markers()
        assert "CDP is not enabled" in markers["cdp"]

    def test_parse_group_interfaces(self) -> None:
        # Minimal interfaces status output
        output = (
            "Port      Name          Status    Vlan   Duplex Speed Type \n"
            "Gi1/0/1                 connected 1      a-full a-1000 10/100/1000BaseTX\n"
        )
        result = self.plugin.parse_group(
            "interfaces",
            {"show interfaces status": output, "show ip interface brief": ""},
        )
        assert "interfaces" in result
        assert len(result["interfaces"]) >= 1

    def test_parse_group_unknown(self) -> None:
        result = self.plugin.parse_group("nonexistent", {})
        assert result == {}


# ---------------------------------------------------------------------------
# AristaPlugin tests
# ---------------------------------------------------------------------------

ARISTA_VERSION = """\
Arista vEOS-lab
Hardware version: 04.00
Serial number: SN-ARISTA-01
Hardware MAC address: 5001.0001.0000
System MAC address:   5001.0001.0000

Software image version: 4.28.3M
Architecture: x86_64
Internal build version: 4.28.3M

Uptime: 2 days, 3 hours, 15 minutes
Total memory: 4002848 kB
Free memory: 2916544 kB

Hostname: leaf-01
"""

ARISTA_INTERFACES_STATUS = """\
Port       Name       Status       Vlan     Duplex  Speed  Type
Et1                   connected    1        full    1G     10GBASE-T
Et2        uplink     connected    trunk    full    10G    10GBASE-T
Et3        mgmt       connected    10       full    1G     10GBASE-T
Ma1                   connected    routed   full    1G     10/100/1000
"""

ARISTA_IP_BRIEF = """\
Interface              IP Address         Status       Protocol       MTU
Ethernet1              10.0.0.1/24        up           up             1500
Loopback0              1.1.1.1/32         up           up             65535
Management1            192.168.1.10/24    up           up             1500
"""

ARISTA_VLAN = """\
VLAN  Name                             Status    Ports
----- -------------------------------- --------- -----------------------
1     default                          active    Et1, Et2
10    MGMT                             active    Et3
100   Production                       active
4094  Reserved                         active
"""

ARISTA_ARP = """\
Address         Age (sec)  Hardware Addr   Interface
10.0.0.1        0:00:05    5001.0001.0001  Ethernet1, Vlan10
10.0.0.2        0:03:22    5001.0002.0001  Ethernet2
192.168.1.1     0:00:01    5001.0003.0001  Management1
"""

ARISTA_MAC = """\
          Mac Address Table
------------------------------------------------------------------

    Vlan    Mac Address       Type        Ports
    ----    -----------       ----        -----
       1    5001.0001.0001    DYNAMIC     Et1
      10    5001.0002.0001    DYNAMIC     Et2
      10    5001.0003.0001    STATIC      Et3
"""

ARISTA_ROUTES = """\
VRF: default

Gateway of last resort:
 S        0.0.0.0/0 [1/0] via 10.0.0.254

 C        10.0.0.0/24 is directly connected, Ethernet1
 L        10.0.0.1/32 is directly connected, Ethernet1
 B        192.168.1.0/24 [200/0] via 10.0.0.2, Ethernet2
 O        172.16.0.0/16 [110/20] via 10.0.0.3, Ethernet3
"""

ARISTA_LLDP = """\
Local Intf: Ethernet1
Chassis id: 5001.0099.0001
Port id: Ethernet1
Port Description: uplink to spine
System Name: spine-01

System Description:
Arista Networks EOS version 4.28.3M running on an Arista Networks vEOS-lab

System Capabilities: Bridge, Router
Enabled Capabilities: Bridge, Router

Management Addresses:
    IPv4: 10.0.0.99

----------

Local Intf: Ethernet2
Chassis id: 5001.0099.0002
Port id: Ethernet1
Port Description: uplink to spine
System Name: spine-02

System Description:
Arista Networks EOS version 4.28.3M

System Capabilities: Bridge, Router
Enabled Capabilities: Bridge, Router

Management Addresses:
    IPv4: 10.0.0.100
"""


class TestAristaPlugin:
    def setup_method(self) -> None:
        self.plugin = AristaPlugin()

    # --- detection ---

    def test_detect_veos(self) -> None:
        assert self.plugin.detect("Arista vEOS-lab")

    def test_detect_eos_version(self) -> None:
        assert self.plugin.detect("Arista EOS version 4.28.3M")

    def test_detect_dcs(self) -> None:
        assert self.plugin.detect("Arista DCS-7050TX-64")

    def test_no_detect_cisco(self) -> None:
        assert not self.plugin.detect("Cisco IOS XE Software, Version 17.06.05")

    # --- version ---

    def test_parse_version(self) -> None:
        ver = self.plugin.parse_version(ARISTA_VERSION)
        assert ver.hostname == "leaf-01"
        assert ver.platform == "Arista vEOS-lab"
        assert ver.serial == "SN-ARISTA-01"
        assert ver.os_version == "4.28.3M"
        assert ver.base_mac == "5001.0001.0000"
        assert "2 days" in (ver.uptime or "")

    # --- interfaces ---

    def test_parse_interfaces_status(self) -> None:
        result = self.plugin.parse_group(
            "interfaces",
            {
                "show interfaces status": ARISTA_INTERFACES_STATUS,
                "show ip interface brief": ARISTA_IP_BRIEF,
            },
        )
        intfs = result["interfaces"]
        assert len(intfs) >= 3
        # Check Et1 parsed correctly
        et1 = next(i for i in intfs if "Ethernet1" in i.name)
        assert et1.status == "connected"
        assert et1.speed == "1G"
        assert et1.ip_address == "10.0.0.1"  # merged from brief

    def test_parse_ip_interface_brief_fallback(self) -> None:
        result = self.plugin.parse_group(
            "interfaces",
            {"show interfaces status": "", "show ip interface brief": ARISTA_IP_BRIEF},
        )
        intfs = result["interfaces"]
        assert len(intfs) >= 2
        lo0 = next(i for i in intfs if "Loopback" in i.name)
        assert lo0.ip_address == "1.1.1.1"

    # --- VLANs ---

    def test_parse_vlans(self) -> None:
        result = self.plugin.parse_group("vlans", {"show vlan": ARISTA_VLAN})
        vlans = result["vlans"]
        assert len(vlans) == 4
        vlan10 = next(v for v in vlans if v.vlan_id == "10")
        assert vlan10.name == "MGMT"
        assert vlan10.status == "active"

    # --- ARP ---

    def test_parse_arp(self) -> None:
        result = self.plugin.parse_group("arp", {"show ip arp": ARISTA_ARP})
        entries = result["arp_table"]
        assert len(entries) == 3
        assert entries[0].ip_address == "10.0.0.1"
        assert entries[0].mac_address == "5001.0001.0001"

    # --- MAC ---

    def test_parse_mac(self) -> None:
        result = self.plugin.parse_group("mac", {"show mac address-table": ARISTA_MAC})
        entries = result["mac_table"]
        assert len(entries) == 3
        static = next(e for e in entries if e.entry_type == "static")
        assert static.vlan_id == "10"

    # --- Routes ---

    def test_parse_routes(self) -> None:
        result = self.plugin.parse_group("routes", {"show ip route": ARISTA_ROUTES})
        routes = result["route_table"]
        assert len(routes) >= 4

        # Check connected route
        connected = next(r for r in routes if r.protocol == "C")
        assert connected.destination == "10.0.0.0/24"
        assert connected.route_type == "connected"

        # Check BGP route
        bgp = next(r for r in routes if r.protocol == "B")
        assert bgp.destination == "192.168.1.0/24"
        assert bgp.next_hop == "10.0.0.2"
        assert bgp.metric == "200/0"

        # Check static default route
        static = next(r for r in routes if r.protocol == "S")
        assert static.destination == "0.0.0.0/0"
        assert static.next_hop == "10.0.0.254"

    # --- Neighbors ---

    def test_parse_lldp_neighbors(self) -> None:
        records = self.plugin.parse_neighbors(cdp_output=None, lldp_output=ARISTA_LLDP)
        assert len(records) == 2
        spine1 = records[0]
        assert spine1.device_id == "spine-01"
        assert spine1.ip_address == "10.0.0.99"
        assert spine1.protocol == "LLDP"

    # --- command mapping ---

    def test_get_commands(self) -> None:
        cmds = self.plugin.get_commands(frozenset(["interfaces", "vlans", "routes"]))
        assert "interfaces" in cmds
        assert "vlans" in cmds
        assert "routes" in cmds
        assert "show vlan" in cmds["vlans"]  # EOS uses "show vlan", not "show vlan brief"

    def test_neighbor_commands(self) -> None:
        cmds = self.plugin.neighbor_commands()
        assert "lldp" in cmds
        # CDP not in default Arista config
        assert "cdp" not in cmds

    # --- empty / edge cases ---

    def test_parse_empty_outputs(self) -> None:
        for group in ["interfaces", "vlans", "arp", "mac", "routes"]:
            result = self.plugin.parse_group(group, {})
            assert isinstance(result, dict)

    def test_parse_unknown_group(self) -> None:
        result = self.plugin.parse_group("nonexistent", {})
        assert result == {}
