# ruff: noqa: E501
"""Canned CLI outputs for simulated Cisco devices in the E2E test topology.

Topology (7 devices):

    CORE-SW-01 (10.0.0.1) ──Gi1/0/1──Gi1/0/1── DIST-SW-01 (10.0.0.2)
    CORE-SW-01 (10.0.0.1) ──Gi1/0/2──Gi1/0/1── DIST-SW-02 (10.0.0.3)
    DIST-SW-01 (10.0.0.2) ──Gi1/0/2──Gi1/0/1── ACCESS-SW-01 (10.0.0.4)
    DIST-SW-01 (10.0.0.2) ──Gi1/0/3──Gi1/0/1── ACCESS-SW-02 (10.0.0.5)
    DIST-SW-02 (10.0.0.3) ──Gi1/0/2──Gi1/0/1── ACCESS-SW-03 (10.0.0.6)
    CORE-SW-01 (10.0.0.1) ──Gi1/0/3──Gi1/0/1── ROUTER-01 (10.0.0.7)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# CORE-SW-01  (10.0.0.1)
# ---------------------------------------------------------------------------

CORE_SW_01_VERSION = """\
Cisco IOS XE Software, Version 17.06.05
Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.06.05, RELEASE SOFTWARE (fc3)
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2023 by Cisco Systems, Inc.
Compiled Mon 20-Nov-23 07:46 by mcpre

ROM: IOS-XE ROMMON
BOOTLDR: System Bootstrap, Version 17.06.05, RELEASE SOFTWARE (P)

CORE-SW-01 upance is 42 days, 3 hours, 15 minutes
CORE-SW-01 uptime is 42 days, 3 hours, 15 minutes
System returned to ROM by Reload Command
System image file is "flash:packages.conf"

cisco C9300-48P (X86) processor with 1419044K/6147K bytes of memory.
Processor board ID FCW2212L04N
2048K bytes of non-volatile configuration memory.
8388608K bytes of physical memory.
1638400K bytes of Crash Files at crashinfo:.
11264000K bytes of Flash at flash:.

Base Ethernet MAC Address: 00aa.bbcc.dd01
"""

CORE_SW_01_CDP = """\
-------------------------
Device ID: DIST-SW-01.corp.local
Entry address(es):
  IP address: 10.0.0.2
Platform: cisco C9200L-48P-4G,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 148 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE

-------------------------
Device ID: DIST-SW-02.corp.local
Entry address(es):
  IP address: 10.0.0.3
Platform: cisco C9200L-48P-4G,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 155 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE

-------------------------
Device ID: ROUTER-01.corp.local
Entry address(es):
  IP address: 10.0.0.7
Platform: cisco ISR4331/K9,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/3,  Port ID (outgoing port): GigabitEthernet0/0/0
Holdtime : 170 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE
"""

CORE_SW_01_INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   TO-DIST-01         connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/2   TO-DIST-02         connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/3   TO-ROUTER-01       connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/4                      notconnect   1          auto    auto   10/100/1000BaseTX
Gi1/0/5                      notconnect   1          auto    auto   10/100/1000BaseTX
"""

CORE_SW_01_VLAN_BRIEF = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Gi1/0/4, Gi1/0/5
10   Management                       active
20   Users                            active
30   Servers                          active
99   Native                           active    Gi1/0/1, Gi1/0/2, Gi1/0/3
"""

CORE_SW_01_IP_INTERFACE_BRIEF = """\
Interface              IP-Address      OK? Method Status                Protocol
Vlan10                 10.0.10.1       YES manual up                    up
Vlan20                 10.0.20.1       YES manual up                    up
Vlan30                 10.0.30.1       YES manual up                    up
GigabitEthernet1/0/1   unassigned      YES unset  up                    up
GigabitEthernet1/0/2   unassigned      YES unset  up                    up
GigabitEthernet1/0/3   unassigned      YES unset  up                    up
"""

CORE_SW_01_ARP = """\
Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  10.0.10.2        5          00aa.bbcc.dd02  ARPA   Vlan10
Internet  10.0.10.3        3          00aa.bbcc.dd03  ARPA   Vlan10
Internet  10.0.20.10       12         00aa.bbcc.ee01  ARPA   Vlan20
Internet  10.0.30.10       1          00aa.bbcc.ff01  ARPA   Vlan30
"""

CORE_SW_01_MAC_TABLE = """\
          Mac Address Table
-------------------------------------------

Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
  10    00aa.bbcc.dd02    DYNAMIC     Gi1/0/1
  10    00aa.bbcc.dd03    DYNAMIC     Gi1/0/2
  20    00aa.bbcc.ee01    DYNAMIC     Gi1/0/1
  30    00aa.bbcc.ff01    DYNAMIC     Gi1/0/2
"""

CORE_SW_01_IP_ROUTE = """\
Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area

Gateway of last resort is 10.0.0.7 to network 0.0.0.0

S*    0.0.0.0/0 [1/0] via 10.0.0.7
C     10.0.0.0/24 is directly connected, Vlan99
L     10.0.0.1/32 is directly connected, Vlan99
C     10.0.10.0/24 is directly connected, Vlan10
L     10.0.10.1/32 is directly connected, Vlan10
C     10.0.20.0/24 is directly connected, Vlan20
L     10.0.20.1/32 is directly connected, Vlan20
C     10.0.30.0/24 is directly connected, Vlan30
L     10.0.30.1/32 is directly connected, Vlan30
"""

CORE_SW_01_TRUNK = """\
Port        Mode             Encapsulation  Status        Native vlan
Gi1/0/1     on               802.1q         trunking      99
Gi1/0/2     on               802.1q         trunking      99
Gi1/0/3     on               802.1q         trunking      99

Port        Vlans allowed on trunk
Gi1/0/1     1-4094
Gi1/0/2     1-4094
Gi1/0/3     1-4094

Port        Vlans allowed and active in management domain
Gi1/0/1     1,10,20,30,99
Gi1/0/2     1,10,20,30,99
Gi1/0/3     1,10,20,30,99
"""

# ---------------------------------------------------------------------------
# DIST-SW-01  (10.0.0.2)
# ---------------------------------------------------------------------------

DIST_SW_01_VERSION = """\
Cisco IOS XE Software, Version 17.06.05
Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.06.05, RELEASE SOFTWARE (fc3)

ROM: IOS-XE ROMMON

DIST-SW-01 uptime is 38 days, 5 hours, 22 minutes
System image file is "flash:packages.conf"

cisco C9200L-48P-4G (X86) processor with 1005825K/6147K bytes of memory.
Processor board ID JAD2330014H

Base Ethernet MAC Address: 00aa.bbcc.dd02
"""

DIST_SW_01_CDP = """\
-------------------------
Device ID: CORE-SW-01.corp.local
Entry address(es):
  IP address: 10.0.0.1
Platform: cisco C9300-48P,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 148 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE

-------------------------
Device ID: ACCESS-SW-01.corp.local
Entry address(es):
  IP address: 10.0.0.4
Platform: cisco C9200L-24P-4G,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 161 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE

-------------------------
Device ID: ACCESS-SW-02.corp.local
Entry address(es):
  IP address: 10.0.0.5
Platform: cisco C9200L-24P-4G,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/3,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 158 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE
"""

DIST_SW_01_INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   TO-CORE-01         connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/2   TO-ACCESS-01       connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/3   TO-ACCESS-02       connected    trunk      a-full  a-1000 10/100/1000BaseTX
"""

DIST_SW_01_VLAN_BRIEF = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active
10   Management                       active
20   Users                            active
99   Native                           active    Gi1/0/1, Gi1/0/2, Gi1/0/3
"""

DIST_SW_01_IP_INTERFACE_BRIEF = """\
Interface              IP-Address      OK? Method Status                Protocol
Vlan10                 10.0.10.2       YES manual up                    up
GigabitEthernet1/0/1   unassigned      YES unset  up                    up
GigabitEthernet1/0/2   unassigned      YES unset  up                    up
GigabitEthernet1/0/3   unassigned      YES unset  up                    up
"""

DIST_SW_01_TRUNK = """\
Port        Mode             Encapsulation  Status        Native vlan
Gi1/0/1     on               802.1q         trunking      99
Gi1/0/2     on               802.1q         trunking      99
Gi1/0/3     on               802.1q         trunking      99

Port        Vlans allowed on trunk
Gi1/0/1     1-4094
Gi1/0/2     1-4094
Gi1/0/3     1-4094
"""

# ---------------------------------------------------------------------------
# DIST-SW-02  (10.0.0.3)
# ---------------------------------------------------------------------------

DIST_SW_02_VERSION = """\
Cisco IOS XE Software, Version 17.06.05
Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.06.05, RELEASE SOFTWARE (fc3)

ROM: IOS-XE ROMMON

DIST-SW-02 uptime is 38 days, 5 hours, 10 minutes
System image file is "flash:packages.conf"

cisco C9200L-48P-4G (X86) processor with 1005825K/6147K bytes of memory.
Processor board ID JAD2330015K

Base Ethernet MAC Address: 00aa.bbcc.dd03
"""

DIST_SW_02_CDP = """\
-------------------------
Device ID: CORE-SW-01.corp.local
Entry address(es):
  IP address: 10.0.0.1
Platform: cisco C9300-48P,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/2
Holdtime : 165 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE

-------------------------
Device ID: ACCESS-SW-03.corp.local
Entry address(es):
  IP address: 10.0.0.6
Platform: cisco C9200L-24P-4G,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 142 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE
"""

DIST_SW_02_INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   TO-CORE-01         connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/2   TO-ACCESS-03       connected    trunk      a-full  a-1000 10/100/1000BaseTX
"""

DIST_SW_02_VLAN_BRIEF = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active
10   Management                       active
30   Servers                          active
99   Native                           active    Gi1/0/1, Gi1/0/2
"""

DIST_SW_02_TRUNK = """\
Port        Mode             Encapsulation  Status        Native vlan
Gi1/0/1     on               802.1q         trunking      99
Gi1/0/2     on               802.1q         trunking      99

Port        Vlans allowed on trunk
Gi1/0/1     1-4094
Gi1/0/2     1-4094
"""

# ---------------------------------------------------------------------------
# ACCESS-SW-01  (10.0.0.4)
# ---------------------------------------------------------------------------

ACCESS_SW_01_VERSION = """\
Cisco IOS XE Software, Version 17.06.05
Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.06.05, RELEASE SOFTWARE (fc3)

ROM: IOS-XE ROMMON

ACCESS-SW-01 uptime is 30 days, 7 hours, 1 minute
System image file is "flash:packages.conf"

cisco C9200L-24P-4G (X86) processor with 1005825K/6147K bytes of memory.
Processor board ID JAD2330016L

Base Ethernet MAC Address: 00aa.bbcc.dd04
"""

ACCESS_SW_01_CDP = """\
-------------------------
Device ID: DIST-SW-01.corp.local
Entry address(es):
  IP address: 10.0.0.2
Platform: cisco C9200L-48P-4G,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/2
Holdtime : 175 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE
"""

ACCESS_SW_01_INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   UPLINK-DIST-01     connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/2   PC-USER-01         connected    20         a-full  a-100  10/100/1000BaseTX
Gi1/0/3   PC-USER-02         connected    20         a-full  a-100  10/100/1000BaseTX
"""

ACCESS_SW_01_VLAN_BRIEF = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active
20   Users                            active    Gi1/0/2, Gi1/0/3
99   Native                           active    Gi1/0/1
"""

ACCESS_SW_01_TRUNK = """\
Port        Mode             Encapsulation  Status        Native vlan
Gi1/0/1     on               802.1q         trunking      99

Port        Vlans allowed on trunk
Gi1/0/1     1-4094
"""

# ---------------------------------------------------------------------------
# ACCESS-SW-02  (10.0.0.5)
# ---------------------------------------------------------------------------

ACCESS_SW_02_VERSION = """\
Cisco IOS XE Software, Version 17.06.05
Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.06.05, RELEASE SOFTWARE (fc3)

ROM: IOS-XE ROMMON

ACCESS-SW-02 uptime is 25 days, 12 hours, 45 minutes
System image file is "flash:packages.conf"

cisco C9200L-24P-4G (X86) processor with 1005825K/6147K bytes of memory.
Processor board ID JAD2330017M

Base Ethernet MAC Address: 00aa.bbcc.dd05
"""

ACCESS_SW_02_CDP = """\
-------------------------
Device ID: DIST-SW-01.corp.local
Entry address(es):
  IP address: 10.0.0.2
Platform: cisco C9200L-48P-4G,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/3
Holdtime : 155 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE
"""

ACCESS_SW_02_INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   UPLINK-DIST-01     connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/2   PC-USER-03         connected    20         a-full  a-100  10/100/1000BaseTX
"""

ACCESS_SW_02_VLAN_BRIEF = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active
20   Users                            active    Gi1/0/2
99   Native                           active    Gi1/0/1
"""

ACCESS_SW_02_TRUNK = """\
Port        Mode             Encapsulation  Status        Native vlan
Gi1/0/1     on               802.1q         trunking      99

Port        Vlans allowed on trunk
Gi1/0/1     1-4094
"""

# ---------------------------------------------------------------------------
# ACCESS-SW-03  (10.0.0.6)
# ---------------------------------------------------------------------------

ACCESS_SW_03_VERSION = """\
Cisco IOS XE Software, Version 17.06.05
Cisco IOS Software [Bengaluru], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.06.05, RELEASE SOFTWARE (fc3)

ROM: IOS-XE ROMMON

ACCESS-SW-03 uptime is 20 days, 1 hour, 30 minutes
System image file is "flash:packages.conf"

cisco C9200L-24P-4G (X86) processor with 1005825K/6147K bytes of memory.
Processor board ID JAD2330018N

Base Ethernet MAC Address: 00aa.bbcc.dd06
"""

ACCESS_SW_03_CDP = """\
-------------------------
Device ID: DIST-SW-02.corp.local
Entry address(es):
  IP address: 10.0.0.3
Platform: cisco C9200L-48P-4G,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/2
Holdtime : 163 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE
"""

ACCESS_SW_03_INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1   UPLINK-DIST-02     connected    trunk      a-full  a-1000 10/100/1000BaseTX
Gi1/0/2   SERVER-01          connected    30         a-full  a-1000 10/100/1000BaseTX
"""

ACCESS_SW_03_VLAN_BRIEF = """\
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active
30   Servers                          active    Gi1/0/2
99   Native                           active    Gi1/0/1
"""

ACCESS_SW_03_TRUNK = """\
Port        Mode             Encapsulation  Status        Native vlan
Gi1/0/1     on               802.1q         trunking      99

Port        Vlans allowed on trunk
Gi1/0/1     1-4094
"""

# ---------------------------------------------------------------------------
# ROUTER-01  (10.0.0.7)
# ---------------------------------------------------------------------------

ROUTER_01_VERSION = """\
Cisco IOS XE Software, Version 17.06.05
Cisco IOS Software [Bengaluru], ISR Software (X86_64_LINUX_IOSD-UNIVERSALK9-M), Version 17.06.05, RELEASE SOFTWARE (fc3)

ROM: IOS-XE ROMMON

ROUTER-01 uptime is 90 days, 2 hours, 55 minutes
System image file is "bootflash:packages.conf"

cisco ISR4331/K9 (1RU) processor with 1687137K/6147K bytes of memory.
Processor board ID FDO21220A4R

Base Ethernet MAC Address: 00aa.bbcc.dd07
"""

ROUTER_01_CDP = """\
-------------------------
Device ID: CORE-SW-01.corp.local
Entry address(es):
  IP address: 10.0.0.1
Platform: cisco C9300-48P,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet0/0/0,  Port ID (outgoing port): GigabitEthernet1/0/3
Holdtime : 170 sec

Version :
Cisco IOS Software, Version 17.06.05, RELEASE SOFTWARE
"""

ROUTER_01_INTERFACES_STATUS = """\
Port      Name               Status       Vlan       Duplex  Speed Type
Gi0/0/0   TO-CORE-01         connected    routed     a-full  a-1000 RJ45
Gi0/0/1   WAN-LINK           connected    routed     a-full  a-1000 RJ45
"""

ROUTER_01_IP_ROUTE = """\
Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP
       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area

Gateway of last resort is 192.168.1.1 to network 0.0.0.0

S*    0.0.0.0/0 [1/0] via 192.168.1.1
C     10.0.0.0/24 is directly connected, GigabitEthernet0/0/0
L     10.0.0.7/32 is directly connected, GigabitEthernet0/0/0
C     192.168.1.0/24 is directly connected, GigabitEthernet0/0/1
L     192.168.1.254/32 is directly connected, GigabitEthernet0/0/1
"""


# ---------------------------------------------------------------------------
# Device registry: IP → (hostname, command_outputs)
# ---------------------------------------------------------------------------

DEVICE_REGISTRY: dict[str, dict[str, str]] = {
    "10.0.0.1": {
        "_hostname": "CORE-SW-01",
        "show version": CORE_SW_01_VERSION,
        "show cdp neighbors detail": CORE_SW_01_CDP,
        "show lldp neighbors detail": "LLDP is not enabled",
        "show interfaces status": CORE_SW_01_INTERFACES_STATUS,
        "show ip interface brief": CORE_SW_01_IP_INTERFACE_BRIEF,
        "show vlan brief": CORE_SW_01_VLAN_BRIEF,
        "show vlan": CORE_SW_01_VLAN_BRIEF,
        "show ip arp": CORE_SW_01_ARP,
        "show arp": CORE_SW_01_ARP,
        "show mac address-table": CORE_SW_01_MAC_TABLE,
        "show ip route": CORE_SW_01_IP_ROUTE,
        "show etherchannel summary": "",
        "show spanning-tree": "",
        "show interfaces trunk": CORE_SW_01_TRUNK,
        "show nve peers": "",
        "show nve vni": "",
        "show bgp l2vpn evpn summary": "",
        "terminal length 0": "",
        "terminal width 512": "",
        "terminal width 0": "",
    },
    "10.0.0.2": {
        "_hostname": "DIST-SW-01",
        "show version": DIST_SW_01_VERSION,
        "show cdp neighbors detail": DIST_SW_01_CDP,
        "show lldp neighbors detail": "LLDP is not enabled",
        "show interfaces status": DIST_SW_01_INTERFACES_STATUS,
        "show ip interface brief": DIST_SW_01_IP_INTERFACE_BRIEF,
        "show vlan brief": DIST_SW_01_VLAN_BRIEF,
        "show vlan": DIST_SW_01_VLAN_BRIEF,
        "show ip arp": "",
        "show arp": "",
        "show mac address-table": "",
        "show ip route": "",
        "show etherchannel summary": "",
        "show spanning-tree": "",
        "show interfaces trunk": DIST_SW_01_TRUNK,
        "show nve peers": "",
        "show nve vni": "",
        "show bgp l2vpn evpn summary": "",
        "terminal length 0": "",
        "terminal width 512": "",
        "terminal width 0": "",
    },
    "10.0.0.3": {
        "_hostname": "DIST-SW-02",
        "show version": DIST_SW_02_VERSION,
        "show cdp neighbors detail": DIST_SW_02_CDP,
        "show lldp neighbors detail": "LLDP is not enabled",
        "show interfaces status": DIST_SW_02_INTERFACES_STATUS,
        "show ip interface brief": "",
        "show vlan brief": DIST_SW_02_VLAN_BRIEF,
        "show vlan": DIST_SW_02_VLAN_BRIEF,
        "show ip arp": "",
        "show arp": "",
        "show mac address-table": "",
        "show ip route": "",
        "show etherchannel summary": "",
        "show spanning-tree": "",
        "show interfaces trunk": DIST_SW_02_TRUNK,
        "show nve peers": "",
        "show nve vni": "",
        "show bgp l2vpn evpn summary": "",
        "terminal length 0": "",
        "terminal width 512": "",
        "terminal width 0": "",
    },
    "10.0.0.4": {
        "_hostname": "ACCESS-SW-01",
        "show version": ACCESS_SW_01_VERSION,
        "show cdp neighbors detail": ACCESS_SW_01_CDP,
        "show lldp neighbors detail": "LLDP is not enabled",
        "show interfaces status": ACCESS_SW_01_INTERFACES_STATUS,
        "show ip interface brief": "",
        "show vlan brief": ACCESS_SW_01_VLAN_BRIEF,
        "show vlan": ACCESS_SW_01_VLAN_BRIEF,
        "show ip arp": "",
        "show arp": "",
        "show mac address-table": "",
        "show ip route": "",
        "show etherchannel summary": "",
        "show spanning-tree": "",
        "show interfaces trunk": ACCESS_SW_01_TRUNK,
        "show nve peers": "",
        "show nve vni": "",
        "show bgp l2vpn evpn summary": "",
        "terminal length 0": "",
        "terminal width 512": "",
        "terminal width 0": "",
    },
    "10.0.0.5": {
        "_hostname": "ACCESS-SW-02",
        "show version": ACCESS_SW_02_VERSION,
        "show cdp neighbors detail": ACCESS_SW_02_CDP,
        "show lldp neighbors detail": "LLDP is not enabled",
        "show interfaces status": ACCESS_SW_02_INTERFACES_STATUS,
        "show ip interface brief": "",
        "show vlan brief": ACCESS_SW_02_VLAN_BRIEF,
        "show vlan": ACCESS_SW_02_VLAN_BRIEF,
        "show ip arp": "",
        "show arp": "",
        "show mac address-table": "",
        "show ip route": "",
        "show etherchannel summary": "",
        "show spanning-tree": "",
        "show interfaces trunk": ACCESS_SW_02_TRUNK,
        "show nve peers": "",
        "show nve vni": "",
        "show bgp l2vpn evpn summary": "",
        "terminal length 0": "",
        "terminal width 512": "",
        "terminal width 0": "",
    },
    "10.0.0.6": {
        "_hostname": "ACCESS-SW-03",
        "show version": ACCESS_SW_03_VERSION,
        "show cdp neighbors detail": ACCESS_SW_03_CDP,
        "show lldp neighbors detail": "LLDP is not enabled",
        "show interfaces status": ACCESS_SW_03_INTERFACES_STATUS,
        "show ip interface brief": "",
        "show vlan brief": ACCESS_SW_03_VLAN_BRIEF,
        "show vlan": ACCESS_SW_03_VLAN_BRIEF,
        "show ip arp": "",
        "show arp": "",
        "show mac address-table": "",
        "show ip route": "",
        "show etherchannel summary": "",
        "show spanning-tree": "",
        "show interfaces trunk": ACCESS_SW_03_TRUNK,
        "show nve peers": "",
        "show nve vni": "",
        "show bgp l2vpn evpn summary": "",
        "terminal length 0": "",
        "terminal width 512": "",
        "terminal width 0": "",
    },
    "10.0.0.7": {
        "_hostname": "ROUTER-01",
        "show version": ROUTER_01_VERSION,
        "show cdp neighbors detail": ROUTER_01_CDP,
        "show lldp neighbors detail": "LLDP is not enabled",
        "show interfaces status": ROUTER_01_INTERFACES_STATUS,
        "show ip interface brief": "",
        "show vlan brief": "",
        "show vlan": "",
        "show ip arp": "",
        "show arp": "",
        "show mac address-table": "",
        "show ip route": ROUTER_01_IP_ROUTE,
        "show etherchannel summary": "",
        "show spanning-tree": "",
        "show interfaces trunk": "",
        "show nve peers": "",
        "show nve vni": "",
        "show bgp l2vpn evpn summary": "",
        "terminal length 0": "",
        "terminal width 512": "",
        "terminal width 0": "",
    },
}

# Valid credentials for the simulated topology
VALID_USERNAME = "admin"
VALID_PASSWORD = "cisco123"
