"""Collection profiles controlling which show commands run per device during discovery.

Profiles define which data to collect beyond the always-required core commands
(show version, CDP/LLDP neighbors). Adapted from Domenion's command_sets.py and
aligned with NetScope's parser capabilities.
"""

from __future__ import annotations

from enum import StrEnum


class CollectionProfile(StrEnum):
    MINIMAL = "minimal"  # version + neighbors only (topology only, fastest)
    STANDARD = "standard"  # + interfaces, VLANs, ARP, MAC (default)
    FULL = "full"  # + routes, EtherChannel, STP, VXLAN (everything)
    CUSTOM = "custom"  # user-selected subset of named groups


# Named command groups beyond the always-run core (show version + CDP/LLDP).
# Keys are used as selectors in custom profile.
COMMAND_GROUPS: dict[str, list[str]] = {
    "interfaces": [
        "show interfaces status",
        "show ip interface brief",
    ],
    "vlans": [
        "show vlan brief",
    ],
    "arp": [
        "show ip arp",
    ],
    "mac": [
        "show mac address-table",
    ],
    "routes": [
        "show ip route",
    ],
    "etherchannel": [
        "show etherchannel summary",
    ],
    "spanning_tree": [
        "show spanning-tree",
    ],
    "trunks": [
        "show interfaces trunk",
    ],
    "vxlan": [
        "show nve peers",
        "show nve vni",
        "show bgp l2vpn evpn summary",
    ],
}

# Which groups each built-in profile activates
_PROFILE_GROUPS: dict[str, list[str]] = {
    CollectionProfile.MINIMAL: [],
    CollectionProfile.STANDARD: ["interfaces", "vlans", "arp", "mac", "routes"],
    CollectionProfile.FULL: [
        "interfaces",
        "vlans",
        "arp",
        "mac",
        "routes",
        "etherchannel",
        "spanning_tree",
        "trunks",
        "vxlan",
    ],
}

# Human-readable descriptions for the frontend
PROFILE_DESCRIPTIONS: dict[str, str] = {
    CollectionProfile.MINIMAL: "Topology only — version + neighbors. Fastest.",
    CollectionProfile.STANDARD: "Standard — adds interfaces, VLANs, ARP, MAC, routing tables.",
    CollectionProfile.FULL: "Full — adds routing, STP, EtherChannel, trunk data, VXLAN/EVPN.",
    CollectionProfile.CUSTOM: "Custom — choose specific data groups to collect.",
}

# Ordered list of all group names for display
ALL_GROUP_NAMES: list[str] = list(COMMAND_GROUPS.keys())


def get_profile_groups(
    profile: CollectionProfile,
    custom_groups: list[str] | None = None,
) -> list[str]:
    """Return the list of active group names for a profile.

    For CUSTOM, uses ``custom_groups`` (unknown names are silently ignored).
    """
    if profile == CollectionProfile.CUSTOM:
        return [g for g in (custom_groups or []) if g in COMMAND_GROUPS]
    return list(_PROFILE_GROUPS[profile])


def get_profile_commands(
    profile: CollectionProfile,
    custom_groups: list[str] | None = None,
) -> list[str]:
    """Return the flat list of show commands for a profile.

    Does NOT include ``show version`` or CDP/LLDP neighbor commands — those
    are always run by the discovery engine regardless of profile.
    """
    commands: list[str] = []
    for group in get_profile_groups(profile, custom_groups):
        commands.extend(COMMAND_GROUPS[group])
    return commands


def groups_for_profile(
    profile: CollectionProfile,
    custom_groups: list[str] | None = None,
) -> frozenset[str]:
    """Return a frozenset of active group names for fast membership testing."""
    return frozenset(get_profile_groups(profile, custom_groups))
