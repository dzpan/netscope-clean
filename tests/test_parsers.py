"""Unit tests for CDP/LLDP/version/interface parsers."""

from backend.discovery import _merge_neighbors
from backend.models import Device, DeviceStatus, NeighborRecord
from backend.normalizer import reconcile_placeholders
from backend.parsers import (
    build_interface_ip_map,
    detect_lldp_platform,
    parse_arp_table,
    parse_bgp_evpn_summary,
    parse_cdp_neighbors,
    parse_etherchannel_summary,
    parse_interfaces_status,
    parse_interfaces_trunk,
    parse_inventory,
    parse_ip_route,
    parse_lldp_neighbors,
    parse_mac_address_table,
    parse_nve_peers,
    parse_nve_vni,
    parse_show_version,
    parse_spanning_tree,
    parse_vlan_brief,
)

# ---------------------------------------------------------------------------
# CDP fixtures
# ---------------------------------------------------------------------------

CDP_DETAIL_OUTPUT = """\
-------------------------
Device ID: SW-CORE-01.corp.local
Entry address(es):
  IP address: 10.0.0.1
Platform: cisco WS-C3850-48P,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet0/1
Holdtime : 148 sec

Version :
Cisco IOS Software, Version 16.12.5a, RELEASE SOFTWARE

-------------------------
Device ID: AP-FLOOR-01
Entry address(es):
  IP address: 10.0.0.50
Platform: cisco AIR-AP2802I-B-K9,  Capabilities: Trans-Bridge
Interface: GigabitEthernet1/0/5,  Port ID (outgoing port): GigabitEthernet0
Holdtime : 162 sec
"""


def test_parse_cdp_neighbors_count():
    records = parse_cdp_neighbors(CDP_DETAIL_OUTPUT)
    assert len(records) == 2


def test_parse_cdp_neighbor_fields():
    records = parse_cdp_neighbors(CDP_DETAIL_OUTPUT)
    sw = records[0]
    assert sw.device_id == "SW-CORE-01"
    assert sw.ip_address == "10.0.0.1"
    assert sw.local_interface == "GigabitEthernet1/0/1"
    assert sw.remote_interface == "GigabitEthernet0/1"
    assert sw.protocol == "CDP"


def test_parse_cdp_ap_neighbor():
    records = parse_cdp_neighbors(CDP_DETAIL_OUTPUT)
    ap = records[1]
    assert ap.device_id == "AP-FLOOR-01"
    assert ap.ip_address == "10.0.0.50"
    assert ap.local_interface == "GigabitEthernet1/0/5"


def test_parse_cdp_empty():
    assert parse_cdp_neighbors("") == []


# CBS / C1200 Small Business CDP format (Device-ID with hyphen, different IP format)
CDP_C1200_OUTPUT = """\
---------------------------------------------
Device-ID: SW-ZUPANC-01.zupanc.com
Advertisement version: 2
Platform: cisco C9200-24T
Capabilities: Router Switch IGMP
Interface: gi1, Port ID (outgoing port): GigabitEthernet1/0/2
Holdtime: 124
Version: Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_LITE_IOSXE), \
Version 17.6.3, RELEASE SOFTWARE (fc4)
Duplex: full
Native VLAN: 1
Primary Management Address: IP 192.168.30.2
Addresses:
          IP 192.168.30.2
---------------------------------------------
Device-ID: AP-Roof
Advertisement version: 2
Platform: cisco C9115AXI-B
Capabilities: Router TransBridge
Interface: gi10, Port ID (outgoing port): GigabitEthernet0
Holdtime: 148
Version: Cisco AP Software, ap1g7-k9w8 Version: 17.15.4.160
Duplex: full
Primary Management Address: IP 192.168.30.102
Addresses:
          IP 192.168.30.102
          IPv6 fe80::497f:a1d2:126:9834 (link-local)
"""


def test_parse_cdp_c1200_count():
    records = parse_cdp_neighbors(CDP_C1200_OUTPUT)
    assert len(records) == 2


def test_parse_cdp_c1200_fields():
    records = parse_cdp_neighbors(CDP_C1200_OUTPUT)
    sw = records[0]
    assert sw.device_id == "SW-ZUPANC-01"
    assert sw.ip_address == "192.168.30.2"
    assert sw.local_interface == "gi1"
    assert sw.remote_interface == "GigabitEthernet1/0/2"
    assert sw.platform == "cisco C9200-24T"


def test_parse_cdp_c1200_ap():
    records = parse_cdp_neighbors(CDP_C1200_OUTPUT)
    ap = records[1]
    assert ap.device_id == "AP-Roof"
    assert ap.ip_address == "192.168.30.102"
    assert ap.local_interface == "gi10"


def test_parse_cdp_no_entries():
    assert parse_cdp_neighbors("Total entries displayed: 0") == []


# ---------------------------------------------------------------------------
# LLDP fixtures
# ---------------------------------------------------------------------------

LLDP_DETAIL_OUTPUT = """\
------------------------------------------------
Local Intf: Gi1/0/2
Chassis id: 00:11:22:33:44:55
Port id: Gi0/2
Port Description: Link to Distribution
System Name: DIST-SW-01

System Description:
Cisco IOS Software, Version 15.2

Time remaining: 100 seconds
System Capabilities: B, R
Enabled Capabilities: B, R
Management Addresses:
    IP: 10.1.0.1

------------------------------------------------
Local Intf: Gi1/0/10
Chassis id: aa:bb:cc:dd:ee:ff
Port id: eth0
System Name: LINUX-SERVER-01

System Capabilities: S
Enabled Capabilities: S
Management Addresses:
    IP: 10.1.0.100
"""


def test_parse_lldp_neighbors_count():
    records = parse_lldp_neighbors(LLDP_DETAIL_OUTPUT)
    assert len(records) == 2


def test_parse_lldp_neighbor_fields():
    records = parse_lldp_neighbors(LLDP_DETAIL_OUTPUT)
    dist = records[0]
    assert dist.device_id == "DIST-SW-01"
    assert dist.local_interface == "Gi1/0/2"
    assert dist.remote_interface == "Gi0/2"
    assert dist.ip_address == "10.1.0.1"
    assert dist.protocol == "LLDP"


def test_parse_lldp_second_neighbor():
    records = parse_lldp_neighbors(LLDP_DETAIL_OUTPUT)
    srv = records[1]
    assert srv.device_id == "LINUX-SERVER-01"
    assert srv.ip_address == "10.1.0.100"


def test_parse_lldp_chassis_id_subtype():
    records = parse_lldp_neighbors(LLDP_DETAIL_OUTPUT)
    dist = records[0]
    assert dist.chassis_id_subtype == "mac"  # 00:11:22:33:44:55
    srv = records[1]
    assert srv.chassis_id_subtype == "mac"  # aa:bb:cc:dd:ee:ff


def test_parse_lldp_port_id_subtype():
    records = parse_lldp_neighbors(LLDP_DETAIL_OUTPUT)
    dist = records[0]
    assert dist.port_id_subtype == "ifName"  # Gi0/2
    srv = records[1]
    assert srv.port_id_subtype == "ifName"  # eth0


def test_parse_lldp_capabilities():
    records = parse_lldp_neighbors(LLDP_DETAIL_OUTPUT)
    dist = records[0]
    assert "bridge" in dist.capabilities
    assert "router" in dist.capabilities
    srv = records[1]
    assert "station" in srv.capabilities


def test_parse_lldp_port_description():
    records = parse_lldp_neighbors(LLDP_DETAIL_OUTPUT)
    dist = records[0]
    assert dist.port_description == "Link to Distribution"
    srv = records[1]
    assert srv.port_description is None  # no port description in fixture


# ---------------------------------------------------------------------------
# Show version fixtures
# ---------------------------------------------------------------------------

SHOW_VERSION_IOSXE = """\
Cisco IOS XE Software, Version 17.03.05
Cisco IOS Software [Amsterdam], Catalyst L3 Switch Software (CAT9K_IOSXE), \
Version 17.3.5, RELEASE SOFTWARE (fc3)
Technical Support: http://www.cisco.com/techsupport

SW-ACCESS-01 uptime is 10 weeks, 3 days, 4 hours, 22 minutes
Uptime for this control processor is 10 weeks, 3 days, 4 hours, 25 minutes
System returned to ROM by reload

cisco C9200L-48PXG-4X (ARM64) processor with 868467K/3071K bytes of memory.
Model number                 : C9200L-48PXG-4X
System serial number         : FCW2345A001
"""


def test_parse_show_version_hostname():
    info = parse_show_version(SHOW_VERSION_IOSXE)
    assert info.hostname == "SW-ACCESS-01"


def test_parse_show_version_serial():
    info = parse_show_version(SHOW_VERSION_IOSXE)
    assert info.serial == "FCW2345A001"


def test_parse_show_version_platform():
    info = parse_show_version(SHOW_VERSION_IOSXE)
    assert "C9200L" in (info.platform or "")


def test_parse_show_version_os():
    info = parse_show_version(SHOW_VERSION_IOSXE)
    assert info.os_version is not None


# ---------------------------------------------------------------------------
# Interfaces status fixtures
# ---------------------------------------------------------------------------

INTF_STATUS_OUTPUT = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   Uplink             connected    trunk        full   1G 10/100/1000BaseTX
Gi1/0/2   Workstation        connected    10           full  100 10/100/1000BaseTX
Gi1/0/3                      notconnect   1            auto   auto 10/100/1000BaseTX
Gi1/0/48  AP-POE             connected    20           full   1G 10/100/1000BaseTX
"""


def test_parse_interfaces_status_count():
    intfs = parse_interfaces_status(INTF_STATUS_OUTPUT)
    assert len(intfs) == 4


def test_parse_interfaces_status_fields():
    intfs = parse_interfaces_status(INTF_STATUS_OUTPUT)
    first = intfs[0]
    assert first.name == "Gi1/0/1"
    assert first.status == "connected"
    assert first.vlan == "trunk"


def test_parse_interfaces_status_notconnect():
    intfs = parse_interfaces_status(INTF_STATUS_OUTPUT)
    third = intfs[2]
    assert third.name == "Gi1/0/3"
    assert third.status == "notconnect"


# ---------------------------------------------------------------------------
# Interfaces status — C1200 / Small Business format
# ---------------------------------------------------------------------------

C1200_INTF_STATUS_OUTPUT = """\
                                                              Flow Link          Back   Mdix
Port     Type         Duplex  Speed Neg      ctrl State       Pressure Mode
-------- ------------ ------  ----- -------- ---- ----------- -------- -------
gi1      1G-Copper    Full    1000  Enabled  Off  Up          Disabled On
gi2      1G-Copper    Full    100   Enabled  Off  Up          Disabled Off
gi3      1G-Copper    Full    100   Enabled  Off  Up          Disabled Off
gi4      1G-Copper      --      --     --     --  Down           --     --
gi5      1G-Copper      --      --     --     --  Down           --     --
gi9      1G-Combo-C     --      --     --     --  Down           --     --
gi10     1G-Combo-C   Full    1000  Enabled  Off  Up          Disabled Off

                                          Flow    Link
Ch       Type    Duplex  Speed  Neg      control  State
-------- ------- ------  -----  -------- -------  -----------
Po1         --     --      --      --       --    Not Present
"""


def test_parse_c1200_intf_count():
    intfs = parse_interfaces_status(C1200_INTF_STATUS_OUTPUT)
    assert len(intfs) == 7


def test_parse_c1200_intf_up():
    intfs = parse_interfaces_status(C1200_INTF_STATUS_OUTPUT)
    gi1 = intfs[0]
    assert gi1.name == "gi1"
    assert gi1.status == "Up"
    assert gi1.speed == "1000"
    assert gi1.duplex == "Full"


def test_parse_c1200_intf_down():
    intfs = parse_interfaces_status(C1200_INTF_STATUS_OUTPUT)
    gi4 = intfs[3]
    assert gi4.name == "gi4"
    assert gi4.status == "Down"


def test_parse_c1200_no_port_channels():
    """Port-channel table after blank line should not be parsed."""
    intfs = parse_interfaces_status(C1200_INTF_STATUS_OUTPUT)
    names = [i.name for i in intfs]
    assert not any(n.startswith("Po") for n in names)


# ---------------------------------------------------------------------------
# Show version — C1200 format
# ---------------------------------------------------------------------------

C1200_VERSION_OUTPUT = """\
Active-image: flash://system/images/image_4.1.3.36.bin
  Version: 4.1.3.36
  MD5 Digest: 90803a985c9110cef9aa4d576206b629
  Date: 19-May-2024
  Time: 08:17:26
Inactive-image: flash://system/images/_image_4.1.3.36.bin
  Version: 4.1.3.36
  MD5 Digest: 90803a985c9110cef9aa4d576206b629
  Date: 19-May-2024
  Time: 08:17:26
"""


def test_parse_c1200_version():
    info = parse_show_version(C1200_VERSION_OUTPUT)
    assert info.os_version == "4.1.3.36"


def test_parse_c1200_version_no_hostname():
    info = parse_show_version(C1200_VERSION_OUTPUT)
    assert info.hostname is None  # C1200 doesn't include hostname in show version


# ---------------------------------------------------------------------------
# VLAN brief fixtures
# ---------------------------------------------------------------------------

VLAN_BRIEF_OUTPUT = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Gi1/0/3
10   Data                             active    Gi1/0/2
20   Voice                            active    Gi1/0/48
100  Management                       active
1002 fddi-default                     act/unsup
"""


def test_parse_vlan_brief_count():
    vlans = parse_vlan_brief(VLAN_BRIEF_OUTPUT)
    assert len(vlans) >= 4


def test_parse_vlan_brief_fields():
    vlans = parse_vlan_brief(VLAN_BRIEF_OUTPUT)
    vlan1 = vlans[0]
    assert vlan1.vlan_id == "1"
    assert vlan1.name == "default"
    assert vlan1.status == "active"


def test_parse_vlan_brief_management():
    vlans = parse_vlan_brief(VLAN_BRIEF_OUTPUT)
    mgmt = next((v for v in vlans if v.vlan_id == "100"), None)
    assert mgmt is not None
    assert mgmt.name == "Management"


# ---------------------------------------------------------------------------
# Show version — NX-OS format (Nexus 9000)
# ---------------------------------------------------------------------------

NXOS_VERSION_OUTPUT = """\
Cisco Nexus Operating System (NX-OS) Software
TAC support: http://www.cisco.com/tac
Documents: http://www.cisco.com/en/US/products/ps9372/tsd_products_support_series_home.html
Copyright (c) 2002-2024, Cisco Systems, Inc. All rights reserved.
The copyrights to certain works contained herein are owned by
other third parties and are used and distributed under license.

Software
  BIOS: version 07.72
  NXOS: version 10.3(1)
  BIOS compile time:  07/19/2023
  NXOS image file is: bootflash:///nxos64-cs.10.3.1.M.bin
  NXOS compile time:  8/17/2023 12:00:00 [08/17/2023 21:13:52]

Hardware
  cisco Nexus9000 C93180YC-FX3 Chassis ("Memory 16254668 kB")
  Intel(R) Xeon(R) CPU D-1530 @ 2.40GHz with 16254668 kB of memory.
  Processor Board ID FDO23456789

  Device name: NXOS-SPINE-01
  bootflash:   53298520 kB
  Kernel uptime is 120 day(s), 3 hour(s), 22 minute(s), 10 second(s)
"""


def test_parse_nxos_version_hostname():
    info = parse_show_version(NXOS_VERSION_OUTPUT)
    assert info.hostname == "NXOS-SPINE-01"


def test_parse_nxos_version_os():
    info = parse_show_version(NXOS_VERSION_OUTPUT)
    assert info.os_version == "10.3(1)"


def test_parse_nxos_version_platform():
    info = parse_show_version(NXOS_VERSION_OUTPUT)
    assert info.platform is not None
    assert "Nexus9000" in info.platform or "Nexus" in info.platform


def test_parse_nxos_version_serial():
    info = parse_show_version(NXOS_VERSION_OUTPUT)
    assert info.serial == "FDO23456789"


# ---------------------------------------------------------------------------
# Show version — NX-OS alternative format (older NX-OS)
# ---------------------------------------------------------------------------

NXOS_VERSION_ALT_OUTPUT = """\
Cisco Nexus Operating System (NX-OS) Software
TAC support: http://www.cisco.com/tac
Copyright (c) 2002-2022, Cisco Systems, Inc. All rights reserved.

Software
  system:    version 9.3(12)
  kickstart: version 9.3(12)
  BIOS:      version 08.42

Hardware
  cisco Nexus 9000 Series Chassis
  Processor Board ID SAL1234ABCD

  Device name: DC-LEAF-02
  bootflash:   51496280 kB
"""


def test_parse_nxos_alt_hostname():
    info = parse_show_version(NXOS_VERSION_ALT_OUTPUT)
    assert info.hostname == "DC-LEAF-02"


def test_parse_nxos_alt_os():
    info = parse_show_version(NXOS_VERSION_ALT_OUTPUT)
    assert info.os_version == "9.3(12)"


def test_parse_nxos_alt_serial():
    info = parse_show_version(NXOS_VERSION_ALT_OUTPUT)
    assert info.serial == "SAL1234ABCD"


# ---------------------------------------------------------------------------
# Uptime extraction from show version
# ---------------------------------------------------------------------------


def test_parse_uptime_iosxe():
    info = parse_show_version(SHOW_VERSION_IOSXE)
    assert info.uptime is not None
    assert "10 weeks" in info.uptime
    assert "3 days" in info.uptime


def test_parse_uptime_nxos():
    info = parse_show_version(NXOS_VERSION_OUTPUT)
    assert info.uptime is not None
    assert "120 day" in info.uptime


def test_parse_uptime_c1200():
    info = parse_show_version(C1200_VERSION_OUTPUT)
    assert info.uptime is None  # C1200 doesn't include uptime in show version


# ---------------------------------------------------------------------------
# Show version — FQDN hostname stripping
# ---------------------------------------------------------------------------

SHOW_VERSION_FQDN = """\
Cisco IOS XE Software, Version 17.06.05

switch1.corp.local uptime is 5 days, 2 hours
System returned to ROM by reload

cisco C9300-48P (X86) processor with 868467K bytes of memory.
Model number                 : C9300-48P
System serial number         : FCW9999A001
"""


def test_parse_show_version_fqdn_stripped():
    """Hostname with domain suffix must be stripped to match CDP/LLDP device_id."""
    info = parse_show_version(SHOW_VERSION_FQDN)
    assert info.hostname == "switch1"


SHOW_VERSION_NO_DOMAIN = """\
Cisco IOS XE Software, Version 17.06.05

switch2 uptime is 1 day, 3 hours
System returned to ROM by reload

cisco C9300-24T (X86) processor with 868467K bytes of memory.
Model number                 : C9300-24T
System serial number         : FCW8888A002
"""


def test_parse_show_version_no_domain_unchanged():
    """Hostname without a domain suffix must be returned as-is."""
    info = parse_show_version(SHOW_VERSION_NO_DOMAIN)
    assert info.hostname == "switch2"


# ---------------------------------------------------------------------------
# Show ip arp
# ---------------------------------------------------------------------------

ARP_OUTPUT = """\
Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  10.0.0.1                -   0cd5.d366.24cc  ARPA   Vlan1
Internet  10.0.0.10              12   aabb.ccdd.eeff  ARPA   Vlan1
Internet  10.0.0.50               5   1122.3344.5566  ARPA   Vlan10
Internet  10.0.1.1                -   dead.beef.cafe  ARPA   GigabitEthernet1/0/1
"""


def test_parse_arp_table_count():
    entries = parse_arp_table(ARP_OUTPUT)
    assert len(entries) == 4


def test_parse_arp_table_fields():
    entries = parse_arp_table(ARP_OUTPUT)
    first = entries[0]
    assert first.ip_address == "10.0.0.1"
    assert first.mac_address == "0cd5.d366.24cc"
    assert first.interface == "Vlan1"
    assert first.entry_type == "static"  # age "-" = static


def test_parse_arp_table_dynamic():
    entries = parse_arp_table(ARP_OUTPUT)
    second = entries[1]
    assert second.entry_type == "dynamic"  # age "12" = dynamic


def test_parse_arp_table_empty():
    assert parse_arp_table("") == []


# ---------------------------------------------------------------------------
# Show mac address-table
# ---------------------------------------------------------------------------

MAC_TABLE_OUTPUT = """\
          Mac Address Table
-------------------------------------------

Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
  10    aabb.ccdd.eeff    DYNAMIC     Gi1/0/1
  10    1122.3344.5566    DYNAMIC     Gi1/0/5
   1    0cd5.d366.24cc    STATIC      Vl1
  20    dead.beef.cafe    DYNAMIC     Gi1/0/48
Total Mac Addresses for this criterion: 4
"""


def test_parse_mac_table_count():
    entries = parse_mac_address_table(MAC_TABLE_OUTPUT)
    assert len(entries) == 4


def test_parse_mac_table_fields():
    entries = parse_mac_address_table(MAC_TABLE_OUTPUT)
    first = entries[0]
    assert first.vlan_id == "10"
    assert first.mac_address == "aabb.ccdd.eeff"
    assert first.interface == "Gi1/0/1"
    assert first.entry_type == "dynamic"


def test_parse_mac_table_empty():
    assert parse_mac_address_table("") == []


# ---------------------------------------------------------------------------
# Build interface IP map
# ---------------------------------------------------------------------------

IP_BRIEF_OUTPUT = """\
Interface              IP-Address      OK? Method Status                Protocol
Vlan1                  10.0.0.1        YES NVRAM  up                    up
Vlan10                 10.0.10.1       YES NVRAM  up                    up
GigabitEthernet1/0/1   unassigned      YES unset  up                    up
GigabitEthernet1/0/2   unassigned      YES unset  down                  down
Loopback0              1.1.1.1         YES NVRAM  up                    up
"""


def test_build_interface_ip_map():
    ip_map = build_interface_ip_map(IP_BRIEF_OUTPUT)
    assert ip_map["Vlan1"] == "10.0.0.1"
    assert ip_map["Vlan10"] == "10.0.10.1"
    assert ip_map["Loopback0"] == "1.1.1.1"
    assert "GigabitEthernet1/0/1" not in ip_map  # unassigned


def test_build_interface_ip_map_empty():
    assert build_interface_ip_map("") == {}


# ---------------------------------------------------------------------------
# Show ip route
# ---------------------------------------------------------------------------

ROUTE_OUTPUT = """\
Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area

Gateway of last resort is 10.0.0.254 to network 0.0.0.0

S*    0.0.0.0/0 [1/0] via 10.0.0.254
      10.0.0.0/8 is variably subnetted, 4 subnets, 3 masks
C        10.0.0.0/24 is directly connected, Vlan1
L        10.0.0.1/32 is directly connected, Vlan1
C        10.0.100.0/24 is directly connected, Vlan100
L        10.0.100.1/32 is directly connected, Vlan100
S        10.1.0.0/16 [1/0] via 10.0.0.254
O        10.2.0.0/24 [110/2] via 10.0.0.2, 00:05:30, Vlan1
"""


def test_parse_ip_route_count():
    entries = parse_ip_route(ROUTE_OUTPUT)
    assert len(entries) == 7


def test_parse_ip_route_connected():
    entries = parse_ip_route(ROUTE_OUTPUT)
    connected = [e for e in entries if e.route_type == "connected"]
    assert len(connected) == 2
    assert connected[0].destination == "10.0.0.0/24"
    assert connected[0].interface == "Vlan1"
    assert connected[0].next_hop is None


def test_parse_ip_route_static_via():
    entries = parse_ip_route(ROUTE_OUTPUT)
    static = [e for e in entries if e.route_type == "static"]
    assert len(static) >= 2
    via_route = next(e for e in static if e.destination == "10.1.0.0/16")
    assert via_route.next_hop == "10.0.0.254"
    assert via_route.metric == "1/0"


def test_parse_ip_route_default():
    entries = parse_ip_route(ROUTE_OUTPUT)
    default = next((e for e in entries if e.destination == "0.0.0.0/0"), None)
    assert default is not None
    assert default.next_hop == "10.0.0.254"
    assert default.route_type == "static"


def test_parse_ip_route_ospf():
    entries = parse_ip_route(ROUTE_OUTPUT)
    ospf = [e for e in entries if e.route_type == "ospf"]
    assert len(ospf) == 1
    assert ospf[0].destination == "10.2.0.0/24"
    assert ospf[0].next_hop == "10.0.0.2"
    assert ospf[0].interface == "Vlan1"


def test_parse_ip_route_empty():
    assert parse_ip_route("") == []


# ---------------------------------------------------------------------------
# Show ip route — NX-OS
# ---------------------------------------------------------------------------

NXOS_ROUTE_OUTPUT = """\
IP Route Table for VRF "default"
'*' denotes best ucast next-hop
'**' denotes best mcast next-hop
'[x/y]' denotes [preference/metric]
'%<string>' in via output denotes VRF <string>

10.0.0.0/24, ubest/mbest: 1/0, attached
    *via 10.0.0.1, Vlan1, [0/0], 2d03h, direct
10.0.0.1/32, ubest/mbest: 1/0, attached
    *via 10.0.0.1, Vlan1, [0/0], 2d03h, local
10.1.0.0/16, ubest/mbest: 1/0
    *via 10.0.0.254, [1/0], 01:30:00, static
0.0.0.0/0, ubest/mbest: 1/0
    *via 10.0.0.1, [1/0], 2d03h, static
10.2.0.0/24, ubest/mbest: 1/0
    *via 10.0.0.2, Eth1/1, [110/41], 00:05:30, ospf-1, intra
"""


def test_parse_nxos_route_count():
    entries = parse_ip_route(NXOS_ROUTE_OUTPUT)
    assert len(entries) == 5


def test_parse_nxos_route_connected():
    entries = parse_ip_route(NXOS_ROUTE_OUTPUT)
    connected = [e for e in entries if e.route_type == "connected"]
    assert len(connected) == 1
    assert connected[0].destination == "10.0.0.0/24"
    assert connected[0].interface == "Vlan1"
    assert connected[0].protocol == "C"


def test_parse_nxos_route_local():
    entries = parse_ip_route(NXOS_ROUTE_OUTPUT)
    local = [e for e in entries if e.route_type == "local"]
    assert len(local) == 1
    assert local[0].destination == "10.0.0.1/32"


def test_parse_nxos_route_static():
    entries = parse_ip_route(NXOS_ROUTE_OUTPUT)
    static = [e for e in entries if e.route_type == "static"]
    assert len(static) == 2
    default = next(e for e in static if e.destination == "0.0.0.0/0")
    assert default.next_hop == "10.0.0.1"


def test_parse_nxos_route_ospf():
    entries = parse_ip_route(NXOS_ROUTE_OUTPUT)
    ospf = [e for e in entries if e.route_type == "ospf"]
    assert len(ospf) == 1
    assert ospf[0].destination == "10.2.0.0/24"
    assert ospf[0].next_hop == "10.0.0.2"
    assert ospf[0].interface == "Eth1/1"
    assert ospf[0].metric == "110/41"


# ---------------------------------------------------------------------------
# Show ip route — CBS/C1200
# ---------------------------------------------------------------------------

CBS_ROUTE_OUTPUT = """\
Maximum Concurrent Equal Cost Paths: 1

 C(directly connected)   S(static)   R(RIP)   O(OSPF)

  S   0.0.0.0/0        via 192.168.1.1                           active
  C   192.168.1.0/24        directly connected, vlan 1            active
  C   192.168.30.0/24       directly connected, vlan 30           active
  S   10.10.0.0/16          via 192.168.1.254                     active
"""


def test_parse_cbs_route_count():
    entries = parse_ip_route(CBS_ROUTE_OUTPUT)
    assert len(entries) == 4


def test_parse_cbs_route_connected():
    entries = parse_ip_route(CBS_ROUTE_OUTPUT)
    connected = [e for e in entries if e.route_type == "connected"]
    assert len(connected) == 2
    assert connected[0].destination == "192.168.1.0/24"
    assert connected[0].interface == "vlan 1"
    assert connected[0].next_hop is None


def test_parse_cbs_route_static():
    entries = parse_ip_route(CBS_ROUTE_OUTPUT)
    static = [e for e in entries if e.route_type == "static"]
    assert len(static) == 2
    default = next(e for e in static if e.destination == "0.0.0.0/0")
    assert default.next_hop == "192.168.1.1"
    assert default.interface is None


def test_parse_cbs_route_static_via():
    entries = parse_ip_route(CBS_ROUTE_OUTPUT)
    static = [e for e in entries if e.destination == "10.10.0.0/16"]
    assert len(static) == 1
    assert static[0].next_hop == "192.168.1.254"
    assert static[0].route_type == "static"


def test_parse_cbs_route_empty():
    assert parse_ip_route("") == []


# ---------------------------------------------------------------------------
# Show etherchannel summary — IOS-XE
# ---------------------------------------------------------------------------

ETHERCHANNEL_IOSXE_OUTPUT = """\
Flags:  D - down        P - bundled in port-channel
        I - stand-alone s - suspended
        H - Hot-standby (LACP only)
        R - Layer3      S - Layer2
        U - in use      N - not in use, no aggregation
        f - failed to allocate aggregator

        M - not in use, minimum links not met
        m - not in use, port not aggregated due to minimum links not met
        u - unsuitable for bundling
        w - waiting to be aggregated
        d - default port

        A - formed by Auto LAG


Number of channel-groups in use: 2
Number of aggregators:           2

Group  Port-channel  Protocol    Ports
------+-------------+-----------+-----------------------------------------------
1      Po1(SU)       LACP        Gi1/0/1(P)    Gi1/0/2(P)
2      Po2(SD)       PAgP        Gi1/0/3(D)    Gi1/0/4(D)
"""


def test_parse_etherchannel_iosxe_count():
    channels = parse_etherchannel_summary(ETHERCHANNEL_IOSXE_OUTPUT)
    assert len(channels) == 2


def test_parse_etherchannel_iosxe_fields():
    channels = parse_etherchannel_summary(ETHERCHANNEL_IOSXE_OUTPUT)
    po1 = channels[0]
    assert po1.channel_id == "1"
    assert po1.port_channel == "Po1"
    assert po1.protocol == "LACP"
    assert po1.status == "up"
    assert po1.layer == "Layer2"
    assert len(po1.members) == 2
    assert po1.members[0].interface == "Gi1/0/1"
    assert po1.members[0].status == "P"
    assert po1.members[0].status_desc == "bundled"


def test_parse_etherchannel_iosxe_down():
    channels = parse_etherchannel_summary(ETHERCHANNEL_IOSXE_OUTPUT)
    po2 = channels[1]
    assert po2.channel_id == "2"
    assert po2.port_channel == "Po2"
    assert po2.protocol == "PAgP"
    assert po2.status == "down"
    assert len(po2.members) == 2
    assert po2.members[0].status == "D"
    assert po2.members[0].status_desc == "down"


# ---------------------------------------------------------------------------
# Show etherchannel summary — NX-OS
# ---------------------------------------------------------------------------

ETHERCHANNEL_NXOS_OUTPUT = """\
Flags:  D - Down        P - Up in port-channel (members)
        I - Individual  H - Hot-standby (LACP only)
        s - Suspended   r - Module-removed
        b - BFD Session Wait
        S - Switched    R - Routed
        U - Up (port-channel)
        p - Up in delay-lacp mode (member)
        M - Not in use. Min-links not met
--------------------------------------------------------------------------------
Group Port-       Type     Protocol  Member Ports
      Channel
--------------------------------------------------------------------------------
1     Po1(SU)     Eth      LACP      Eth1/1(P)    Eth1/2(P)
2     Po2(RU)     Eth      LACP      Eth1/3(P)    Eth1/4(P)    Eth1/5(P)
"""


def test_parse_etherchannel_nxos_count():
    channels = parse_etherchannel_summary(ETHERCHANNEL_NXOS_OUTPUT)
    assert len(channels) == 2


def test_parse_etherchannel_nxos_fields():
    channels = parse_etherchannel_summary(ETHERCHANNEL_NXOS_OUTPUT)
    po1 = channels[0]
    assert po1.channel_id == "1"
    assert po1.port_channel == "Po1"
    assert po1.protocol == "LACP"
    assert po1.status == "up"
    assert po1.layer == "Layer2"
    assert len(po1.members) == 2
    assert po1.members[0].interface == "Eth1/1"


def test_parse_etherchannel_nxos_layer3():
    channels = parse_etherchannel_summary(ETHERCHANNEL_NXOS_OUTPUT)
    po2 = channels[1]
    assert po2.layer == "Layer3"
    assert po2.status == "up"
    assert len(po2.members) == 3


def test_parse_etherchannel_nxos_three_members():
    channels = parse_etherchannel_summary(ETHERCHANNEL_NXOS_OUTPUT)
    po2 = channels[1]
    assert po2.members[0].interface == "Eth1/3"
    assert po2.members[1].interface == "Eth1/4"
    assert po2.members[2].interface == "Eth1/5"


# ---------------------------------------------------------------------------
# Show etherchannel summary — edge cases
# ---------------------------------------------------------------------------


def test_parse_etherchannel_empty():
    assert parse_etherchannel_summary("") == []


def test_parse_etherchannel_no_groups():
    output = """\
Number of channel-groups in use: 0
Number of aggregators:           0

Group  Port-channel  Protocol    Ports
------+-------------+-----------+-----------------------------------------------
"""
    assert parse_etherchannel_summary(output) == []


# ---------------------------------------------------------------------------
# NX-OS CDP fixture (hardening — no parser changes expected)
# ---------------------------------------------------------------------------

NXOS_CDP_OUTPUT = """\
----------------------------------------
Device ID:NXOS-LEAF-01.dc.local
System Name: NXOS-LEAF-01
Interface address(es):
    IPv4 Address: 10.1.1.2
Platform: N9K-C93180YC-FX3, Capabilities: Router Switch IGMP Filtering Supports-STP-Dispute
Interface: Ethernet1/1, Port ID (outgoing port): Ethernet1/49
Holdtime: 132 sec

Version:
Cisco Nexus Operating System (NX-OS) Software, Version 10.3(1)

Advertisement Version: 2
VTP Management Domain: ''

----------------------------------------
Device ID:NXOS-LEAF-02.dc.local
System Name: NXOS-LEAF-02
Interface address(es):
    IPv4 Address: 10.1.1.3
Platform: N9K-C93180YC-FX3, Capabilities: Router Switch IGMP
Interface: Ethernet1/2, Port ID (outgoing port): Ethernet1/49
Holdtime: 161 sec
"""


def test_parse_nxos_cdp_count():
    records = parse_cdp_neighbors(NXOS_CDP_OUTPUT)
    assert len(records) == 2


def test_parse_nxos_cdp_fields():
    records = parse_cdp_neighbors(NXOS_CDP_OUTPUT)
    leaf1 = records[0]
    assert leaf1.device_id == "NXOS-LEAF-01"
    assert leaf1.ip_address == "10.1.1.2"
    assert leaf1.local_interface == "Ethernet1/1"
    assert leaf1.remote_interface == "Ethernet1/49"
    assert leaf1.protocol == "CDP"


def test_parse_nxos_cdp_second():
    records = parse_cdp_neighbors(NXOS_CDP_OUTPUT)
    leaf2 = records[1]
    assert leaf2.device_id == "NXOS-LEAF-02"
    assert leaf2.ip_address == "10.1.1.3"


# ---------------------------------------------------------------------------
# NX-OS LLDP fixture (hardening)
# ---------------------------------------------------------------------------

NXOS_LLDP_OUTPUT = """\
Capability codes:
  (R) Router, (B) Bridge, (T) Telephone, (C) DOCSIS Cable Device
  (W) WLAN Access Point, (P) Repeater, (S) Station, (O) Other
Device ID            Local Intf      Hold-time  Capability  Port ID

Chassis id: 00:aa:bb:cc:dd:01
Port id: Eth1/49
Local Intf: Eth1/1
Port Description: uplink-to-spine
System Name: NXOS-LEAF-01

System Description:
Cisco Nexus Operating System (NX-OS) Software 10.3(1)

Time remaining: 108 seconds
System Capabilities: B, R
Enabled Capabilities: B, R
Management Addresses:
    IP: 10.1.1.2

------------------------------------------------
Chassis id: 00:aa:bb:cc:dd:02
Port id: Eth1/49
Local Intf: Eth1/2
Port Description: uplink-to-spine
System Name: NXOS-LEAF-02

System Description:
Cisco Nexus Operating System (NX-OS) Software 10.3(1)

Management Addresses:
    IP: 10.1.1.3

------------------------------------------------
Chassis id: 00:aa:bb:cc:dd:03
Port id: Eth1/50
Local Intf: Eth1/3
Port Description: peer-link
System Name: NXOS-SPINE-02

Management Addresses:
    IP: 10.1.1.4
"""


def test_parse_nxos_lldp_count():
    records = parse_lldp_neighbors(NXOS_LLDP_OUTPUT)
    assert len(records) == 3


def test_parse_nxos_lldp_fields():
    records = parse_lldp_neighbors(NXOS_LLDP_OUTPUT)
    leaf1 = records[0]
    assert leaf1.device_id == "NXOS-LEAF-01"
    assert leaf1.ip_address == "10.1.1.2"
    assert leaf1.local_interface == "Eth1/1"
    assert leaf1.remote_interface == "Eth1/49"
    assert leaf1.protocol == "LLDP"


def test_parse_nxos_lldp_third():
    records = parse_lldp_neighbors(NXOS_LLDP_OUTPUT)
    spine2 = records[2]
    assert spine2.device_id == "NXOS-SPINE-02"
    assert spine2.ip_address == "10.1.1.4"


def test_parse_nxos_lldp_capabilities():
    records = parse_lldp_neighbors(NXOS_LLDP_OUTPUT)
    leaf1 = records[0]
    assert "bridge" in leaf1.capabilities
    assert "router" in leaf1.capabilities


def test_parse_nxos_lldp_port_description():
    records = parse_lldp_neighbors(NXOS_LLDP_OUTPUT)
    leaf1 = records[0]
    assert leaf1.port_description == "uplink-to-spine"


def test_parse_nxos_lldp_chassis_id_subtype():
    records = parse_lldp_neighbors(NXOS_LLDP_OUTPUT)
    leaf1 = records[0]
    assert leaf1.chassis_id_subtype == "mac"  # 00:aa:bb:cc:dd:01


# ---------------------------------------------------------------------------
# NX-OS interface status fixture (hardening)
# ---------------------------------------------------------------------------

NXOS_INTF_STATUS_OUTPUT = """\
Port          Name               Status    Vlan      Duplex  Speed   Type
--------------------------------------------------------------------------------
Eth1/1        uplink-leaf-01     connected trunk     full    100G    QSFP-100G-AOC3M
Eth1/2        uplink-leaf-02     connected trunk     full    100G    QSFP-100G-AOC3M
Eth1/3        peer-link          connected trunk     full    100G    QSFP-100G-AOC3M
Eth1/49       mgmt-uplink        connected 1         full    10G     SFP-H10GB-CU3M
"""


def test_parse_nxos_intf_count():
    intfs = parse_interfaces_status(NXOS_INTF_STATUS_OUTPUT)
    assert len(intfs) == 4


def test_parse_nxos_intf_fields():
    intfs = parse_interfaces_status(NXOS_INTF_STATUS_OUTPUT)
    eth1 = intfs[0]
    assert eth1.name == "Eth1/1"
    assert eth1.status == "connected"
    assert eth1.vlan == "trunk"


def test_parse_nxos_intf_speed():
    intfs = parse_interfaces_status(NXOS_INTF_STATUS_OUTPUT)
    assert intfs[0].speed == "100G"
    assert intfs[3].speed == "10G"


def test_parse_nxos_intf_vlan():
    intfs = parse_interfaces_status(NXOS_INTF_STATUS_OUTPUT)
    assert intfs[3].vlan == "1"


# ---------------------------------------------------------------------------
# NX-OS VLAN brief fixture (hardening)
# ---------------------------------------------------------------------------

NXOS_VLAN_BRIEF_OUTPUT = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Eth1/49
1001 VXLAN-Prod                       active
1002 VXLAN-Dev                        active
"""


def test_parse_nxos_vlan_count():
    vlans = parse_vlan_brief(NXOS_VLAN_BRIEF_OUTPUT)
    assert len(vlans) == 3


def test_parse_nxos_vlan_fields():
    vlans = parse_vlan_brief(NXOS_VLAN_BRIEF_OUTPUT)
    prod = next(v for v in vlans if v.vlan_id == "1001")
    assert prod.name == "VXLAN-Prod"
    assert prod.status == "active"


# ---------------------------------------------------------------------------
# Show nve peers (VXLAN)
# ---------------------------------------------------------------------------

NVE_PEERS_OUTPUT = """\
Interface Peer-IP          State LearnType Uptime   Router-Mac
--------- ---------------  ----- --------- -------- -----------------
nve1      10.1.1.2         Up    CP        1d02h    5254.0012.3456
nve1      10.1.1.3         Up    CP        2d05h    5254.0012.3457
nve1      10.1.1.4         Down  CP        00:00:00 n/a
"""


def test_parse_nve_peers_count():
    peers = parse_nve_peers(NVE_PEERS_OUTPUT)
    assert len(peers) == 3


def test_parse_nve_peers_up_fields():
    peers = parse_nve_peers(NVE_PEERS_OUTPUT)
    p = peers[0]
    assert p.interface == "nve1"
    assert p.peer_ip == "10.1.1.2"
    assert p.state == "Up"
    assert p.learn_type == "CP"
    assert p.uptime == "1d02h"
    assert p.router_mac == "5254.0012.3456"


def test_parse_nve_peers_down():
    peers = parse_nve_peers(NVE_PEERS_OUTPUT)
    p = peers[2]
    assert p.state == "Down"
    assert p.router_mac == "n/a"


def test_parse_nve_peers_empty():
    assert parse_nve_peers("") == []


def test_parse_nve_peers_no_peers():
    output = """\
Interface Peer-IP          State LearnType Uptime   Router-Mac
--------- ---------------  ----- --------- -------- -----------------
"""
    assert parse_nve_peers(output) == []


# ---------------------------------------------------------------------------
# Show nve vni (VXLAN)
# ---------------------------------------------------------------------------

NVE_VNI_OUTPUT = """\
Codes: CP - Control Plane        DP - Data Plane
       UC - Unconfigured         SA - Suppress ARP

Interface VNI      Multicast-group   State Mode Type  [BD/VRF]      Flags
--------- -------- ----------------- ----- ---- ----- ------------- -----
nve1      50001    UnicastBGP        Up    CP   L2 [1001]
nve1      50002    UnicastBGP        Up    CP   L2 [1002]
nve1      50100    n/a               Up    CP   L3 [Tenant-VRF]
"""


def test_parse_nve_vni_count():
    vnis = parse_nve_vni(NVE_VNI_OUTPUT)
    assert len(vnis) == 3


def test_parse_nve_vni_l2():
    vnis = parse_nve_vni(NVE_VNI_OUTPUT)
    v = vnis[0]
    assert v.interface == "nve1"
    assert v.vni == "50001"
    assert v.multicast_group == "UnicastBGP"
    assert v.state == "Up"
    assert v.vni_type == "L2 [1001]"
    assert v.bd_vrf == "1001"


def test_parse_nve_vni_l3():
    vnis = parse_nve_vni(NVE_VNI_OUTPUT)
    v = vnis[2]
    assert v.vni == "50100"
    assert v.vni_type == "L3 [Tenant-VRF]"
    assert v.bd_vrf == "Tenant-VRF"


def test_parse_nve_vni_empty():
    assert parse_nve_vni("") == []


# ---------------------------------------------------------------------------
# Show bgp l2vpn evpn summary (VXLAN)
# ---------------------------------------------------------------------------

BGP_EVPN_OUTPUT = """\
BGP summary information for VRF default, address family L2VPN EVPN
BGP router identifier 10.1.1.1, local AS number 65001
BGP table version is 100, L2VPN EVPN config peers 2, capable peers 2
5 network entries and 5 paths using 1220 bytes of memory
BGP attribute entries [3/516], BGP AS path entries [0/0]

Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
10.1.1.2        4 65001   12345   12300      100    0    0 1d02h    100
10.1.1.3        4 65001    9876    9800      100    0    0 2d05h    85
"""


def test_parse_bgp_evpn_count():
    neighbors = parse_bgp_evpn_summary(BGP_EVPN_OUTPUT)
    assert len(neighbors) == 2


def test_parse_bgp_evpn_fields():
    neighbors = parse_bgp_evpn_summary(BGP_EVPN_OUTPUT)
    n = neighbors[0]
    assert n.neighbor == "10.1.1.2"
    assert n.asn == "65001"
    assert n.version == "4"
    assert n.msg_rcvd == "12345"
    assert n.msg_sent == "12300"
    assert n.up_down == "1d02h"
    assert n.state_pfx_rcv == "100"


def test_parse_bgp_evpn_second():
    neighbors = parse_bgp_evpn_summary(BGP_EVPN_OUTPUT)
    n = neighbors[1]
    assert n.neighbor == "10.1.1.3"
    assert n.state_pfx_rcv == "85"


def test_parse_bgp_evpn_empty():
    assert parse_bgp_evpn_summary("") == []


def test_parse_bgp_evpn_no_peers():
    output = """\
BGP summary information for VRF default, address family L2VPN EVPN
BGP router identifier 10.1.1.1, local AS number 65001

Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
"""
    assert parse_bgp_evpn_summary(output) == []


# ---------------------------------------------------------------------------
# Show spanning-tree — IOS-XE (multi-VLAN: root + non-root)
# ---------------------------------------------------------------------------

STP_IOSXE_OUTPUT = """\
VLAN0001
  Spanning tree enabled protocol rstp
  Root ID    Priority    32769
             Address     0cd5.d366.2400
             This bridge is the root
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

  Bridge ID  Priority    32769  (priority 32768 sys-id-ext 1)
             Address     0cd5.d366.2400
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
Gi1/0/1             Desg FWD 4         128.1    P2p
Gi1/0/2             Desg FWD 4         128.2    P2p

VLAN0010
  Spanning tree enabled protocol rstp
  Root ID    Priority    24586
             Address     0cd5.d366.2400
             Cost        4
             Port        1 (GigabitEthernet1/0/1)
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

  Bridge ID  Priority    32778  (priority 32768 sys-id-ext 10)
             Address     aabb.ccdd.ee00
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

Interface           Role Sts Cost      Prio.Nbr Type
------------------- ---- --- --------- -------- --------------------------------
Gi1/0/1             Root FWD 4         128.1    P2p
Gi1/0/2             Desg FWD 4         128.2    P2p
Gi1/0/3             Altn BLK 4         128.3    P2p
"""


def test_parse_stp_iosxe_vlan_count():
    vlans = parse_spanning_tree(STP_IOSXE_OUTPUT)
    assert len(vlans) == 2


def test_parse_stp_iosxe_root_detection():
    vlans = parse_spanning_tree(STP_IOSXE_OUTPUT)
    vlan1 = vlans[0]
    assert vlan1.vlan_id == "1"
    assert vlan1.is_root is True
    assert vlan1.protocol == "rstp"


def test_parse_stp_iosxe_root_bridge_fields():
    vlans = parse_spanning_tree(STP_IOSXE_OUTPUT)
    vlan1 = vlans[0]
    assert vlan1.root_priority == "32769"
    assert vlan1.root_address == "0cd5.d366.2400"
    assert vlan1.root_cost == "0"  # is root, so cost = 0
    assert vlan1.bridge_priority == "32769"
    assert vlan1.bridge_address == "0cd5.d366.2400"


def test_parse_stp_iosxe_non_root():
    vlans = parse_spanning_tree(STP_IOSXE_OUTPUT)
    vlan10 = vlans[1]
    assert vlan10.vlan_id == "10"
    assert vlan10.is_root is False
    assert vlan10.root_priority == "24586"
    assert vlan10.root_address == "0cd5.d366.2400"
    assert vlan10.root_cost == "4"
    assert vlan10.bridge_priority == "32778"
    assert vlan10.bridge_address == "aabb.ccdd.ee00"


def test_parse_stp_iosxe_root_ports():
    vlans = parse_spanning_tree(STP_IOSXE_OUTPUT)
    vlan1 = vlans[0]
    assert len(vlan1.ports) == 2
    assert all(p.role == "Desg" for p in vlan1.ports)
    assert all(p.state == "FWD" for p in vlan1.ports)


def test_parse_stp_iosxe_non_root_ports():
    vlans = parse_spanning_tree(STP_IOSXE_OUTPUT)
    vlan10 = vlans[1]
    assert len(vlan10.ports) == 3
    root_port = next(p for p in vlan10.ports if p.role == "Root")
    assert root_port.interface == "GigabitEthernet1/0/1"
    assert root_port.state == "FWD"
    assert root_port.cost == "4"
    assert root_port.port_priority == "128.1"
    assert root_port.link_type == "P2p"


def test_parse_stp_iosxe_blocked_port():
    vlans = parse_spanning_tree(STP_IOSXE_OUTPUT)
    vlan10 = vlans[1]
    blocked = [p for p in vlan10.ports if p.state == "BLK"]
    assert len(blocked) == 1
    assert blocked[0].interface == "GigabitEthernet1/0/3"
    assert blocked[0].role == "Altn"


def test_parse_stp_empty():
    assert parse_spanning_tree("") == []


def test_parse_stp_no_stp():
    assert parse_spanning_tree("No spanning tree instance exists.") == []


# ---------------------------------------------------------------------------
# Show spanning-tree — NX-OS (single VLAN, root bridge)
# ---------------------------------------------------------------------------

STP_NXOS_OUTPUT = """\
VLAN0001
  Spanning tree enabled protocol rstp
  Root ID    Priority    32769
             Address     5254.0012.3456
             This bridge is the root
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

  Bridge ID  Priority    32769  (priority 32768 sys-id-ext 1)
             Address     5254.0012.3456
             Hello Time   2 sec  Max Age 20 sec  Forward Delay 15 sec

Interface           Role Sts Cost      Guard    Type
------------------- ---- --- --------- -------- --------------------------------
Eth1/1              Desg FWD 4         None     P2p
Eth1/2              Desg FWD 4         None     P2p
Eth1/3              Desg FWD 4         Loop     P2p Edge
"""


def test_parse_stp_nxos_count():
    vlans = parse_spanning_tree(STP_NXOS_OUTPUT)
    assert len(vlans) == 1


def test_parse_stp_nxos_is_root():
    vlans = parse_spanning_tree(STP_NXOS_OUTPUT)
    assert vlans[0].is_root is True
    assert vlans[0].vlan_id == "1"


def test_parse_stp_nxos_ports():
    vlans = parse_spanning_tree(STP_NXOS_OUTPUT)
    ports = vlans[0].ports
    assert len(ports) == 3
    assert ports[0].interface == "Ethernet1/1"
    assert ports[0].role == "Desg"
    assert ports[0].state == "FWD"
    assert ports[0].cost == "4"


def test_parse_stp_nxos_guard_column():
    """NX-OS uses Guard column instead of Prio.Nbr — parser should handle it."""
    vlans = parse_spanning_tree(STP_NXOS_OUTPUT)
    ports = vlans[0].ports
    # Guard values ("None", "Loop") are captured in port_priority field
    assert ports[0].port_priority == "None"
    assert ports[2].port_priority == "Loop"
    assert ports[2].link_type == "P2p Edge"


# ---------------------------------------------------------------------------
# show version — base_mac
# ---------------------------------------------------------------------------

VERSION_WITH_BASE_MAC = """\
SW-CORE-01 uptime is 10 weeks, 3 days, 4 hours, 22 minutes
...
Base Ethernet MAC Address         : 0cd5.d366.2400
...
Cisco IOS Software [Amsterdam], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.3.4a
...
System Serial Number              : FCW2144L00Z
"""

VERSION_NXOS_SYSTEM_MAC = """\
  Device name: NXOS-SPINE-01
  system:    version 10.3(1)
  ...
  System MAC Address:  0cd5.d366.2400
"""

VERSION_NO_MAC = """\
SW-ACCESS-01 uptime is 5 days, 2 hours
Cisco IOS Software, Version 15.2(4)E7
"""


def test_parse_show_version_base_mac_iosxe():
    info = parse_show_version(VERSION_WITH_BASE_MAC)
    assert info.base_mac == "0cd5.d366.2400"


def test_parse_show_version_base_mac_nxos():
    info = parse_show_version(VERSION_NXOS_SYSTEM_MAC)
    assert info.base_mac == "0cd5.d366.2400"


def test_parse_show_version_no_base_mac():
    info = parse_show_version(VERSION_NO_MAC)
    assert info.base_mac is None


# ---------------------------------------------------------------------------
# show inventory
# ---------------------------------------------------------------------------

INVENTORY_OUTPUT = """\
NAME: "Chassis", DESCR: "Cisco Catalyst 3850-48P Switch"
PID: WS-C3850-48P      , VID: V02  , SN: FCW1234A0BC

NAME: "Switch 1 - Power Supply 1", DESCR: "Switch 1 - Power Supply 1"
PID: PWR-C1-1100WAC    , VID: V01  , SN: LIT9876B0CD

NAME: "Switch 1 - FRU Uplink Module 1", DESCR: "4x1G Uplink Module"
PID: C3850-NM-4-1G     , VID: V04  , SN: FCW5678C0DE
"""

INVENTORY_EMPTY = "No items found\n"


def test_parse_inventory_count():
    items = parse_inventory(INVENTORY_OUTPUT)
    assert len(items) == 3


def test_parse_inventory_chassis():
    items = parse_inventory(INVENTORY_OUTPUT)
    chassis = items[0]
    assert chassis.name == "Chassis"
    assert chassis.description == "Cisco Catalyst 3850-48P Switch"
    assert chassis.pid == "WS-C3850-48P"
    assert chassis.vid == "V02"
    assert chassis.serial == "FCW1234A0BC"


def test_parse_inventory_module():
    items = parse_inventory(INVENTORY_OUTPUT)
    mod = items[2]
    assert mod.name == "Switch 1 - FRU Uplink Module 1"
    assert mod.pid == "C3850-NM-4-1G"
    assert mod.serial == "FCW5678C0DE"


def test_parse_inventory_empty():
    assert parse_inventory(INVENTORY_EMPTY) == []


def test_parse_inventory_no_pid():
    """Items without a PID line should still be returned."""
    output = 'NAME: "Sensor", DESCR: "Temperature Sensor"\n'
    items = parse_inventory(output)
    assert len(items) == 1
    assert items[0].pid is None


C1200_INVENTORY_OUTPUT = """\
NAME: "Chassis", DESCR: "C1200-8T-E-2G"
PID: C1200-8T-E-2G     , VID: V01  , SN: ABC1234567
"""


def test_parse_c1200_inventory_platform():
    """C1200 show inventory provides the platform model via Chassis PID."""
    items = parse_inventory(C1200_INVENTORY_OUTPUT)
    assert len(items) == 1
    chassis = items[0]
    assert chassis.name == "Chassis"
    assert chassis.pid == "C1200-8T-E-2G"


def test_c1200_version_platform_is_none():
    """C1200 show version does not contain platform — fallback needed."""
    info = parse_show_version(C1200_VERSION_OUTPUT)
    assert info.platform is None


# ---------------------------------------------------------------------------
# show interfaces trunk
# ---------------------------------------------------------------------------

TRUNK_OUTPUT = """\
Port        Mode             Encapsulation  Status        Native vlan
Gi1/0/1     on               802.1q         trunking      1
Gi1/0/2     desirable        n-802.1q       not-trunking  1

Port        Vlans allowed on trunk
Gi1/0/1     1-4094
Gi1/0/2     1-4094

Port        Vlans allowed and active in management domain
Gi1/0/1     1,10,20,30
Gi1/0/2     1

Port        Vlans in spanning tree forwarding state and not pruned
Gi1/0/1     1,10,20
Gi1/0/2     none
"""

TRUNK_EMPTY = ""


def test_parse_interfaces_trunk_keys():
    trunks = parse_interfaces_trunk(TRUNK_OUTPUT)
    assert set(trunks.keys()) == {"Gi1/0/1", "Gi1/0/2"}


def test_parse_interfaces_trunk_status():
    trunks = parse_interfaces_trunk(TRUNK_OUTPUT)
    gi1 = trunks["Gi1/0/1"]
    assert gi1.mode == "on"
    assert gi1.encapsulation == "802.1q"
    assert gi1.status == "trunking"
    assert gi1.native_vlan == "1"


def test_parse_interfaces_trunk_vlans():
    trunks = parse_interfaces_trunk(TRUNK_OUTPUT)
    gi1 = trunks["Gi1/0/1"]
    assert gi1.allowed_vlans == "1-4094"
    assert gi1.active_vlans == "1,10,20,30"
    assert gi1.forwarding_vlans == "1,10,20"


def test_parse_interfaces_trunk_not_trunking():
    trunks = parse_interfaces_trunk(TRUNK_OUTPUT)
    gi2 = trunks["Gi1/0/2"]
    assert gi2.status == "not-trunking"
    assert gi2.mode == "desirable"


def test_parse_interfaces_trunk_empty():
    assert parse_interfaces_trunk(TRUNK_EMPTY) == {}


# NX-OS show interfaces trunk fixture
TRUNK_NXOS_OUTPUT = """\
--------------------------------------------------------------------------------
Port          Native Vlan  Status        Port Channel
--------------------------------------------------------------------------------
Eth1/1        1            trunking      --
Eth1/2        100          trunking      Po1
Eth1/3        1            not-trunking  --

--------------------------------------------------------------------------------
Port          Vlans Allowed on Trunk
--------------------------------------------------------------------------------
Eth1/1        1-3967,4048-4093
Eth1/2        1,100,200

--------------------------------------------------------------------------------
Port          Vlans Err-disabled on Trunk
--------------------------------------------------------------------------------

--------------------------------------------------------------------------------
Port          STP Forwarding
--------------------------------------------------------------------------------
Eth1/1        1,100,200
Eth1/2        100,200
"""


def test_parse_interfaces_trunk_nxos_keys():
    trunks = parse_interfaces_trunk(TRUNK_NXOS_OUTPUT)
    assert {"Eth1/1", "Eth1/2", "Eth1/3"}.issubset(trunks.keys())


def test_parse_interfaces_trunk_nxos_native_vlan():
    trunks = parse_interfaces_trunk(TRUNK_NXOS_OUTPUT)
    assert trunks["Eth1/1"].native_vlan == "1"
    assert trunks["Eth1/2"].native_vlan == "100"


def test_parse_interfaces_trunk_nxos_status():
    trunks = parse_interfaces_trunk(TRUNK_NXOS_OUTPUT)
    assert trunks["Eth1/1"].status == "trunking"
    assert trunks["Eth1/3"].status == "not-trunking"


def test_parse_interfaces_trunk_nxos_allowed_vlans():
    trunks = parse_interfaces_trunk(TRUNK_NXOS_OUTPUT)
    assert trunks["Eth1/1"].allowed_vlans == "1-3967,4048-4093"
    assert trunks["Eth1/2"].allowed_vlans == "1,100,200"


def test_parse_interfaces_trunk_nxos_forwarding():
    trunks = parse_interfaces_trunk(TRUNK_NXOS_OUTPUT)
    assert trunks["Eth1/1"].forwarding_vlans == "1,100,200"
    assert trunks["Eth1/2"].forwarding_vlans == "100,200"


def test_parse_interfaces_trunk_nxos_no_mode():
    """NX-OS does not expose mode/encapsulation — should remain None."""
    trunks = parse_interfaces_trunk(TRUNK_NXOS_OUTPUT)
    assert trunks["Eth1/1"].mode is None
    assert trunks["Eth1/1"].encapsulation is None


# ---------------------------------------------------------------------------
# CBS / C1200 — show vlan (no Status column)
# ---------------------------------------------------------------------------

CBS_VLAN_OUTPUT = """\
 VLAN  Name                 Tagged Ports    Untagged Ports  Created By
 ----  -------------------  --------------- ---------------  ----------
 1     default                              gi1-8            Default
 10    Management           gi1             gi9,gi10         Manual
 20    Cameras                              gi4-6            Manual
 30    IoT                  gi1,gi2                          Manual
"""


def test_parse_cbs_vlan_count():
    vlans = parse_vlan_brief(CBS_VLAN_OUTPUT)
    assert len(vlans) == 4


def test_parse_cbs_vlan_fields():
    vlans = parse_vlan_brief(CBS_VLAN_OUTPUT)
    v1 = vlans[0]
    assert v1.vlan_id == "1"
    assert v1.name == "default"
    assert v1.status == "active"


def test_parse_cbs_vlan_named():
    vlans = parse_vlan_brief(CBS_VLAN_OUTPUT)
    mgmt = next((v for v in vlans if v.vlan_id == "10"), None)
    assert mgmt is not None
    assert mgmt.name == "Management"
    assert mgmt.status == "active"


def test_parse_cbs_vlan_all_active():
    """CBS show vlan has no Status column — all entries should be active."""
    vlans = parse_vlan_brief(CBS_VLAN_OUTPUT)
    assert all(v.status == "active" for v in vlans)


# ---------------------------------------------------------------------------
# CBS / C1200 — show arp (hyphen MAC, VLAN column)
# ---------------------------------------------------------------------------

CBS_ARP_OUTPUT = """\
 IP address        MAC address        VLAN     Type       Age (m)
 -----------------------------------------------------------------
 192.168.30.1      00-1e-49-e3-52-cc  1        Dynamic    2
 192.168.30.50     88-94-71-e5-85-4c  1        Dynamic    0
 192.168.30.100    c8-4b-d6-aa-bb-cc  30       Static     -
"""


def test_parse_cbs_arp_count():
    entries = parse_arp_table(CBS_ARP_OUTPUT)
    assert len(entries) == 3


def test_parse_cbs_arp_fields():
    entries = parse_arp_table(CBS_ARP_OUTPUT)
    first = entries[0]
    assert first.ip_address == "192.168.30.1"
    assert first.mac_address == "00-1e-49-e3-52-cc"
    assert first.interface == "Vlan1"
    assert first.entry_type == "dynamic"


def test_parse_cbs_arp_static():
    entries = parse_arp_table(CBS_ARP_OUTPUT)
    static = next((e for e in entries if e.entry_type == "static"), None)
    assert static is not None
    assert static.ip_address == "192.168.30.100"
    assert static.interface == "Vlan30"


def test_parse_cbs_arp_empty():
    assert parse_arp_table("") == []


# ---------------------------------------------------------------------------
# CBS / C1200 — show mac address-table (hyphen MAC notation)
# ---------------------------------------------------------------------------

CBS_MAC_TABLE_OUTPUT = """\
 Aging time is 300 sec

 VLAN   MAC address         Port type    Ports
 -----  -----------------   ----------  -------
 1      00-1e-49-e3-52-cc   Dynamic      gi1
 10     88-94-71-e5-85-4c   Dynamic      gi2
 10     c8-4b-d6-aa-bb-cc   Dynamic      gi3
 1      f4-4d-30-11-22-33   Management   --
"""


def test_parse_cbs_mac_count():
    """Management entries and '--' ports should be excluded."""
    entries = parse_mac_address_table(CBS_MAC_TABLE_OUTPUT)
    assert len(entries) == 3


def test_parse_cbs_mac_fields():
    entries = parse_mac_address_table(CBS_MAC_TABLE_OUTPUT)
    first = entries[0]
    assert first.vlan_id == "1"
    assert first.mac_address == "00-1e-49-e3-52-cc"
    assert first.interface == "gi1"
    assert first.entry_type == "dynamic"


def test_parse_cbs_mac_vlan10():
    entries = parse_mac_address_table(CBS_MAC_TABLE_OUTPUT)
    vlan10 = [e for e in entries if e.vlan_id == "10"]
    assert len(vlan10) == 2
    ports = {e.interface for e in vlan10}
    assert ports == {"gi2", "gi3"}


def test_parse_cbs_mac_empty():
    assert parse_mac_address_table("") == []


# ---------------------------------------------------------------------------
# Dual-protocol merge/dedup tests
# ---------------------------------------------------------------------------


def test_merge_neighbors_dedup_same_port_and_ip():
    """When CDP and LLDP report the same neighbor on the same port, keep one."""
    cdp = [
        NeighborRecord(
            device_id="SW1",
            ip_address="10.0.0.1",
            local_interface="Gi1/0/1",
            remote_interface="Gi0/1",
            platform="WS-C3850",
            protocol="CDP",
        )
    ]
    lldp = [
        NeighborRecord(
            device_id="SW1",
            ip_address="10.0.0.1",
            local_interface="Gi1/0/1",
            remote_interface="Gi0/1",
            platform="Cisco IOS",
            protocol="LLDP",
            chassis_id_subtype="mac",
            capabilities=["bridge", "router"],
            port_description="uplink",
        )
    ]
    merged = _merge_neighbors(cdp, lldp)
    assert len(merged) == 1
    # LLDP should win because it has richer metadata
    assert merged[0].protocol == "LLDP"
    assert merged[0].capabilities == ["bridge", "router"]


def test_merge_neighbors_different_ports():
    """Neighbors on different local ports should both be kept."""
    cdp = [
        NeighborRecord(
            device_id="SW1",
            ip_address="10.0.0.1",
            local_interface="Gi1/0/1",
            protocol="CDP",
        )
    ]
    lldp = [
        NeighborRecord(
            device_id="SW2",
            ip_address="10.0.0.2",
            local_interface="Gi1/0/2",
            protocol="LLDP",
        )
    ]
    merged = _merge_neighbors(cdp, lldp)
    assert len(merged) == 2


def test_merge_neighbors_empty_inputs():
    """Empty inputs should produce empty output."""
    assert _merge_neighbors([], []) == []


def test_merge_neighbors_cdp_only():
    """CDP-only results pass through unchanged."""
    cdp = [
        NeighborRecord(
            device_id="SW1",
            ip_address="10.0.0.1",
            local_interface="Gi1/0/1",
            protocol="CDP",
        )
    ]
    merged = _merge_neighbors(cdp, [])
    assert len(merged) == 1
    assert merged[0].protocol == "CDP"


def test_merge_neighbors_lldp_only():
    """LLDP-only results pass through unchanged."""
    lldp = [
        NeighborRecord(
            device_id="SW1",
            ip_address="10.0.0.1",
            local_interface="Gi1/0/1",
            protocol="LLDP",
            capabilities=["bridge"],
        )
    ]
    merged = _merge_neighbors([], lldp)
    assert len(merged) == 1
    assert merged[0].protocol == "LLDP"


# ---------------------------------------------------------------------------
# IOS-XR LLDP fixture
# ---------------------------------------------------------------------------

IOSXR_LLDP_OUTPUT = """\
------------------------------------------------
Local Intf: GigabitEthernet0/0/0/0
Chassis id: 0011.2233.4455
Port id: GigabitEthernet0/0/0/1
Port Description: Uplink to core
System Name: IOSXR-ROUTER-01

System Description:
Cisco IOS XR Software, Version 7.3.2

Time remaining: 107 seconds
System Capabilities: B, R
Enabled Capabilities: R
Management Addresses:
    IPv4: 10.10.0.1

------------------------------------------------
Local Intf: GigabitEthernet0/0/0/2
Chassis id: 0011.2233.4466
Port id: Gi0/0/0/3
System Name:

System Description:
Cisco IOS XR Software, Version 7.3.2

Management Addresses:
    IPv4: 10.10.0.2
"""


def test_parse_iosxr_lldp_count():
    records = parse_lldp_neighbors(IOSXR_LLDP_OUTPUT)
    assert len(records) == 2


def test_parse_iosxr_lldp_fields():
    records = parse_lldp_neighbors(IOSXR_LLDP_OUTPUT)
    r = records[0]
    assert r.device_id == "IOSXR-ROUTER-01"
    assert r.local_interface == "GigabitEthernet0/0/0/0"
    assert r.remote_interface == "GigabitEthernet0/0/0/1"
    assert r.ip_address == "10.10.0.1"
    assert r.protocol == "LLDP"
    assert r.port_description == "Uplink to core"
    assert r.chassis_id == "0011.2233.4455"


def test_parse_iosxr_lldp_chassis_id_fallback():
    """When System Name is empty, chassis_id should be used as device_id."""
    records = parse_lldp_neighbors(IOSXR_LLDP_OUTPUT)
    r = records[1]
    # System Name is empty, so device_id falls back to chassis_id
    assert r.device_id == "0011.2233.4466"
    assert r.chassis_id_subtype == "mac"


def test_parse_iosxr_lldp_capabilities():
    records = parse_lldp_neighbors(IOSXR_LLDP_OUTPUT)
    r = records[0]
    assert "router" in r.capabilities
    # Enabled Capabilities is "R" only, not "B, R"
    assert "bridge" not in r.capabilities


def test_parse_iosxr_lldp_ipv4_label():
    """IOS-XR uses 'IPv4:' instead of 'IP:' for management address."""
    records = parse_lldp_neighbors(IOSXR_LLDP_OUTPUT)
    assert records[0].ip_address == "10.10.0.1"
    assert records[1].ip_address == "10.10.0.2"


# ---------------------------------------------------------------------------
# Arista EOS LLDP fixture
# ---------------------------------------------------------------------------

EOS_LLDP_OUTPUT = """\
------------------------------------------------
Local Intf: Ethernet1
Chassis id: 00:1c:73:aa:bb:cc
Port id: Ethernet2
Port Description: leaf-to-spine link
System Name: ARISTA-LEAF-01

System Description:
Arista Networks EOS version 4.28.3M

Time remaining: 120 seconds
System Capabilities: B, R
Enabled Capabilities: B, R
Management Addresses:
    IP: 10.20.0.1

LLDP-MED Device Type: Endpoint Class II
Power requested: 15.4 Watts
Power allocated: 15.4 Watts
Network Policy: VLAN 100, DSCP 46
Port VLAN ID: 100
VLAN Name: Management
Link Aggregation: Supported, Enabled
Aggregated Port ID: 7

------------------------------------------------
Local Intf: Ethernet49
Chassis id: 00:1c:73:dd:ee:ff
Port id: Ethernet49
System Name: ARISTA-SPINE-01

System Description:
Arista Networks EOS version 4.28.3M

Enabled Capabilities: R
Management Addresses:
    IP: 10.20.0.254
"""


def test_parse_eos_lldp_count():
    records = parse_lldp_neighbors(EOS_LLDP_OUTPUT)
    assert len(records) == 2


def test_parse_eos_lldp_fields():
    records = parse_lldp_neighbors(EOS_LLDP_OUTPUT)
    leaf = records[0]
    assert leaf.device_id == "ARISTA-LEAF-01"
    assert leaf.local_interface == "Ethernet1"
    assert leaf.remote_interface == "Ethernet2"
    assert leaf.ip_address == "10.20.0.1"
    assert leaf.chassis_id == "00:1c:73:aa:bb:cc"


def test_parse_eos_lldp_med_tlvs():
    records = parse_lldp_neighbors(EOS_LLDP_OUTPUT)
    leaf = records[0]
    assert leaf.med_device_type == "class-ii"
    assert leaf.med_poe_requested == 15.4
    assert leaf.med_poe_allocated == 15.4
    assert leaf.med_network_policy == "VLAN 100, DSCP 46"


def test_parse_eos_lldp_vlan_tlvs():
    records = parse_lldp_neighbors(EOS_LLDP_OUTPUT)
    leaf = records[0]
    assert leaf.vlan_id == 100
    assert leaf.vlan_name == "Management"


def test_parse_eos_lldp_lag_tlvs():
    records = parse_lldp_neighbors(EOS_LLDP_OUTPUT)
    leaf = records[0]
    assert leaf.lag_supported is True
    assert leaf.lag_enabled is True
    assert leaf.lag_port_channel_id == 7


def test_parse_eos_lldp_no_tlvs():
    """Second neighbor has no MED/VLAN/LAG TLVs."""
    records = parse_lldp_neighbors(EOS_LLDP_OUTPUT)
    spine = records[1]
    assert spine.med_device_type is None
    assert spine.vlan_id is None
    assert spine.lag_supported is None


# ---------------------------------------------------------------------------
# Juniper JunOS LLDP fixture
# ---------------------------------------------------------------------------

JUNOS_LLDP_OUTPUT = """\
Local Interface    : ge-0/0/0
Chassis ID         : 00:05:86:71:a0:01
Port ID            : ge-0/0/1
Port Description   : Core uplink
System Name        : JUNOS-SW-01
System Description : Juniper Networks, Inc. ex4300-48t
Supported capabilities : Router Bridge
Management Address : 10.30.0.1

Local Interface    : ge-0/0/2
Chassis ID         : 00:05:86:71:b0:02
Port ID            : ge-0/0/3
System Name        : JUNOS-SW-02
System Description : Juniper Networks, Inc. qfx5100-48s
Management Address : 10.30.0.2
"""


def test_parse_junos_lldp_count():
    records = parse_lldp_neighbors(JUNOS_LLDP_OUTPUT)
    assert len(records) == 2


def test_parse_junos_lldp_platform_detection():
    assert detect_lldp_platform(JUNOS_LLDP_OUTPUT) == "junos"


def test_parse_junos_lldp_fields():
    records = parse_lldp_neighbors(JUNOS_LLDP_OUTPUT)
    sw1 = records[0]
    assert sw1.device_id == "JUNOS-SW-01"
    assert sw1.local_interface == "ge-0/0/0"
    assert sw1.remote_interface == "ge-0/0/1"
    assert sw1.ip_address == "10.30.0.1"
    assert sw1.protocol == "LLDP"
    assert sw1.chassis_id == "00:05:86:71:a0:01"
    assert sw1.port_description == "Core uplink"


def test_parse_junos_lldp_capabilities():
    records = parse_lldp_neighbors(JUNOS_LLDP_OUTPUT)
    sw1 = records[0]
    assert "router" in sw1.capabilities
    assert "bridge" in sw1.capabilities


def test_parse_junos_lldp_second():
    records = parse_lldp_neighbors(JUNOS_LLDP_OUTPUT)
    sw2 = records[1]
    assert sw2.device_id == "JUNOS-SW-02"
    assert sw2.ip_address == "10.30.0.2"


# ---------------------------------------------------------------------------
# HP/Aruba ProCurve LLDP fixture
# ---------------------------------------------------------------------------

HP_LLDP_OUTPUT = """\
LocalPort : 1
ChassisId : 00 11 22 33 44 55
SysName   : HP-SWITCH-01
PortId    : 2
PortDescr : Uplink-to-core
SysDescr  : HP J9772A Switch 2530-48G
MgmtAddr  : 10.40.0.1
System Capabilities: B
Enabled Capabilities: B

LocalPort : 5
ChassisId : aa:bb:cc:dd:ee:ff
SysName   : HP-SWITCH-02
PortId    : 10
PortDescr : Server-link
SysDescr  : HP J9773A Switch 2530-24G
MgmtAddr  : 10.40.0.2
"""


def test_parse_hp_lldp_count():
    records = parse_lldp_neighbors(HP_LLDP_OUTPUT)
    assert len(records) == 2


def test_parse_hp_lldp_platform_detection():
    assert detect_lldp_platform(HP_LLDP_OUTPUT) == "hp"


def test_parse_hp_lldp_fields():
    records = parse_lldp_neighbors(HP_LLDP_OUTPUT)
    sw1 = records[0]
    assert sw1.device_id == "HP-SWITCH-01"
    assert sw1.local_interface == "1"
    assert sw1.remote_interface == "2"
    assert sw1.ip_address == "10.40.0.1"
    assert sw1.protocol == "LLDP"
    assert sw1.port_description == "Uplink-to-core"


def test_parse_hp_lldp_chassis_id_space_separated():
    """HP uses space-separated MAC: '00 11 22 33 44 55'."""
    records = parse_lldp_neighbors(HP_LLDP_OUTPUT)
    sw1 = records[0]
    assert sw1.chassis_id == "00:11:22:33:44:55"
    assert sw1.chassis_id_subtype == "mac"


def test_parse_hp_lldp_capabilities():
    records = parse_lldp_neighbors(HP_LLDP_OUTPUT)
    sw1 = records[0]
    assert "bridge" in sw1.capabilities


def test_parse_hp_lldp_second():
    records = parse_lldp_neighbors(HP_LLDP_OUTPUT)
    sw2 = records[1]
    assert sw2.device_id == "HP-SWITCH-02"
    assert sw2.chassis_id == "aa:bb:cc:dd:ee:ff"


# ---------------------------------------------------------------------------
# Edge cases: chassis-ID-only, multi-chassis, LLDP disabled
# ---------------------------------------------------------------------------

LLDP_CHASSIS_ID_ONLY = """\
------------------------------------------------
Local Intf: Gi1/0/5
Chassis id: 0022.3344.5566
Port id: 1
Port Description: Access port

Enabled Capabilities: B
Management Addresses:
    IP: 10.50.0.1
"""


def test_parse_lldp_chassis_id_only():
    """Device with no System Name — chassis_id becomes device_id."""
    records = parse_lldp_neighbors(LLDP_CHASSIS_ID_ONLY)
    assert len(records) == 1
    r = records[0]
    assert r.device_id == "0022.3344.5566"
    assert r.chassis_id == "0022.3344.5566"
    assert r.chassis_id_subtype == "mac"
    assert r.port_id_subtype == "local"  # port_id is "1" (digit)


LLDP_DISABLED_OUTPUT = """\
% LLDP is not enabled
"""


def test_parse_lldp_disabled():
    """LLDP disabled returns empty list."""
    records = parse_lldp_neighbors(LLDP_DISABLED_OUTPUT)
    assert records == []


LLDP_MULTI_CHASSIS_OUTPUT = """\
------------------------------------------------
Local Intf: Gi1/0/1
Chassis id: 00:aa:bb:01:01:01
Port id: Gi1/0/48
Port Description: Stack member 1
System Name: STACK-SW-01

Enabled Capabilities: B, R
Management Addresses:
    IP: 10.60.0.1

------------------------------------------------
Local Intf: Gi2/0/1
Chassis id: 00:aa:bb:02:02:02
Port id: Gi2/0/48
Port Description: Stack member 2
System Name: STACK-SW-01

Enabled Capabilities: B, R
Management Addresses:
    IP: 10.60.0.1
"""


def test_parse_lldp_multi_chassis():
    """Multi-chassis stack: same System Name but different Chassis IDs."""
    records = parse_lldp_neighbors(LLDP_MULTI_CHASSIS_OUTPUT)
    assert len(records) == 2
    assert records[0].device_id == "STACK-SW-01"
    assert records[1].device_id == "STACK-SW-01"
    assert records[0].chassis_id == "00:aa:bb:01:01:01"
    assert records[1].chassis_id == "00:aa:bb:02:02:02"
    # Same IP (stack virtual IP)
    assert records[0].ip_address == "10.60.0.1"
    assert records[1].ip_address == "10.60.0.1"


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def test_detect_platform_cisco():
    assert detect_lldp_platform(LLDP_DETAIL_OUTPUT) == "cisco"
    assert detect_lldp_platform(NXOS_LLDP_OUTPUT) == "cisco"
    assert detect_lldp_platform(IOSXR_LLDP_OUTPUT) == "cisco"


def test_detect_platform_eos():
    """EOS uses same format as Cisco — detected as cisco."""
    assert detect_lldp_platform(EOS_LLDP_OUTPUT) == "cisco"


# ---------------------------------------------------------------------------
# Chassis ID MAC reconciliation
# ---------------------------------------------------------------------------


def test_reconcile_chassis_mac_matching():
    """Placeholder resolved via chassis MAC when IP matching fails."""
    from backend.models import Link

    real_device = Device(
        id="REAL-SW-01",
        hostname="REAL-SW-01",
        mgmt_ip="10.0.0.1",
        status=DeviceStatus.OK,
        base_mac="aa:bb:cc:dd:ee:ff",
    )
    placeholder = Device(
        id="aabb.ccdd.eeff",
        hostname="aabb.ccdd.eeff",
        mgmt_ip="unknown",
        status=DeviceStatus.PLACEHOLDER,
    )
    link = Link(
        source="MY-SW",
        target="aabb.ccdd.eeff",
        source_intf="Gi1/0/1",
        target_intf="Gi0/1",
        protocol="LLDP",
    )
    neighbors = [
        NeighborRecord(
            device_id="aabb.ccdd.eeff",
            local_interface="Gi1/0/1",
            protocol="LLDP",
            chassis_id="aabb.ccdd.eeff",
            chassis_id_subtype="mac",
        ),
    ]
    devices, links_out = reconcile_placeholders(
        [real_device, placeholder], [link], neighbors=neighbors
    )
    # Placeholder should be merged into real device
    assert len(devices) == 1
    assert devices[0].id == "REAL-SW-01"
    # Link target rewritten
    assert links_out[0].target == "REAL-SW-01"


def test_reconcile_ip_still_preferred():
    """IP-based reconciliation still works (backwards compat)."""
    from backend.models import Link

    real_device = Device(
        id="SW-01",
        hostname="SW-01",
        mgmt_ip="10.0.0.5",
        status=DeviceStatus.OK,
    )
    placeholder = Device(
        id="0cd5d36624cc",
        hostname="0cd5d36624cc",
        mgmt_ip="10.0.0.5",
        status=DeviceStatus.PLACEHOLDER,
    )
    link = Link(
        source="SW-02",
        target="0cd5d36624cc",
        source_intf="Gi1/0/1",
        protocol="CDP",
    )
    devices, links_out = reconcile_placeholders([real_device, placeholder], [link])
    assert len(devices) == 1
    assert devices[0].id == "SW-01"
    assert links_out[0].target == "SW-01"


# ---------------------------------------------------------------------------
# IOS-XR local interface format variant
# ---------------------------------------------------------------------------


def test_parse_iosxr_local_interface_label():
    """IOS-XR uses 'Local Interface:' instead of 'Local Intf:'."""
    output = """\
------------------------------------------------
Local Interface: TenGigE0/0/0/0
Chassis id: aa:bb:cc:11:22:33
Port id: TenGigE0/0/0/1
System Name: XR-CORE-01

Enabled Capabilities: R
Management Addresses:
    IP: 10.99.0.1
"""
    # 'Local Interface:' should NOT match the Cisco parser (it needs 'Local Intf:')
    # but our parser checks "local interface" case-insensitively
    records = parse_lldp_neighbors(output)
    assert len(records) == 1
    assert records[0].device_id == "XR-CORE-01"


# ---------------------------------------------------------------------------
# Error-path / edge-case tests
# ---------------------------------------------------------------------------


class TestParserErrorPaths:
    def test_parse_cdp_empty_input(self) -> None:
        from backend.parsers import parse_cdp_neighbors

        assert parse_cdp_neighbors("") == []

    def test_parse_cdp_garbage_input(self) -> None:
        from backend.parsers import parse_cdp_neighbors

        assert parse_cdp_neighbors("zzzz\x00\xff random garbage data !@#$") == []

    def test_parse_lldp_partial_output(self) -> None:
        from backend.parsers import parse_lldp_neighbors

        partial = "Local Intf: Gi1/0/1\nChassis id: aabb.ccdd"
        result = parse_lldp_neighbors(partial)
        assert isinstance(result, list)

    def test_parse_vlan_brief_truncated(self) -> None:
        from backend.parsers import parse_vlan_brief

        truncated = (
            "VLAN Name                             Status    Ports\n"
            "---- ----\n"
            "1    default                          active    Gi1/0/1"
        )
        result = parse_vlan_brief(truncated)
        assert isinstance(result, list)

    def test_parse_routes_no_routes(self) -> None:
        from backend.parsers import parse_ip_route

        no_routes = "Gateway of last resort is not set"
        result = parse_ip_route(no_routes)
        assert result == []
