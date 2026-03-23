"""Unit tests for collection profile command generation."""

from backend.command_sets import (
    ALL_GROUP_NAMES,
    COMMAND_GROUPS,
    CollectionProfile,
    get_profile_commands,
    get_profile_groups,
    groups_for_profile,
)

# ---------------------------------------------------------------------------
# Profile group membership
# ---------------------------------------------------------------------------


def test_minimal_profile_has_no_extra_groups() -> None:
    groups = get_profile_groups(CollectionProfile.MINIMAL)
    assert groups == []


def test_standard_profile_groups() -> None:
    groups = get_profile_groups(CollectionProfile.STANDARD)
    assert set(groups) == {"interfaces", "vlans", "arp", "mac", "routes"}


def test_full_profile_includes_all_standard_plus_extras() -> None:
    standard = set(get_profile_groups(CollectionProfile.STANDARD))
    full = set(get_profile_groups(CollectionProfile.FULL))
    assert standard.issubset(full)
    # Full must also include at least routes, etherchannel, spanning_tree, vxlan
    assert {"routes", "etherchannel", "spanning_tree", "vxlan"}.issubset(full)


def test_full_profile_covers_all_groups() -> None:
    full = set(get_profile_groups(CollectionProfile.FULL))
    assert full == set(ALL_GROUP_NAMES)


# ---------------------------------------------------------------------------
# Custom profile
# ---------------------------------------------------------------------------


def test_custom_profile_uses_supplied_groups() -> None:
    groups = get_profile_groups(CollectionProfile.CUSTOM, custom_groups=["arp", "mac"])
    assert groups == ["arp", "mac"]


def test_custom_profile_ignores_unknown_groups() -> None:
    groups = get_profile_groups(
        CollectionProfile.CUSTOM,
        custom_groups=["arp", "nonexistent_group"],
    )
    assert "nonexistent_group" not in groups
    assert "arp" in groups


def test_custom_profile_empty_groups_returns_empty() -> None:
    groups = get_profile_groups(CollectionProfile.CUSTOM, custom_groups=[])
    assert groups == []


def test_custom_profile_none_groups_returns_empty() -> None:
    groups = get_profile_groups(CollectionProfile.CUSTOM, custom_groups=None)
    assert groups == []


# ---------------------------------------------------------------------------
# Profile commands (flat list)
# ---------------------------------------------------------------------------


def test_minimal_profile_has_no_commands() -> None:
    cmds = get_profile_commands(CollectionProfile.MINIMAL)
    assert cmds == []


def test_standard_profile_includes_interface_commands() -> None:
    cmds = get_profile_commands(CollectionProfile.STANDARD)
    assert "show interfaces status" in cmds
    assert "show vlan brief" in cmds
    assert "show ip arp" in cmds
    assert "show mac address-table" in cmds


def test_standard_profile_excludes_full_only_commands() -> None:
    cmds = get_profile_commands(CollectionProfile.STANDARD)
    assert "show ip route" in cmds
    assert "show spanning-tree" not in cmds
    assert "show nve peers" not in cmds


def test_full_profile_includes_all_commands() -> None:
    cmds = get_profile_commands(CollectionProfile.FULL)
    # Should include everything from standard
    std_cmds = get_profile_commands(CollectionProfile.STANDARD)
    for c in std_cmds:
        assert c in cmds
    # And the extras
    assert "show ip route" in cmds
    assert "show spanning-tree" in cmds
    assert "show etherchannel summary" in cmds
    assert "show nve peers" in cmds
    assert "show nve vni" in cmds
    assert "show bgp l2vpn evpn summary" in cmds


def test_custom_profile_commands() -> None:
    cmds = get_profile_commands(CollectionProfile.CUSTOM, custom_groups=["routes", "spanning_tree"])
    assert "show ip route" in cmds
    assert "show spanning-tree" in cmds
    assert "show interfaces status" not in cmds


def test_no_duplicate_commands_in_any_profile() -> None:
    for profile in CollectionProfile:
        cmds = get_profile_commands(profile)
        assert len(cmds) == len(set(cmds)), f"Duplicate commands in {profile} profile"


# ---------------------------------------------------------------------------
# groups_for_profile (frozenset helper)
# ---------------------------------------------------------------------------


def test_groups_for_profile_returns_frozenset() -> None:
    result = groups_for_profile(CollectionProfile.STANDARD)
    assert isinstance(result, frozenset)
    assert "interfaces" in result


def test_groups_for_profile_custom() -> None:
    result = groups_for_profile(CollectionProfile.CUSTOM, custom_groups=["vxlan"])
    assert result == frozenset({"vxlan"})


# ---------------------------------------------------------------------------
# COMMAND_GROUPS consistency
# ---------------------------------------------------------------------------


def test_all_group_commands_are_strings() -> None:
    for group, cmds in COMMAND_GROUPS.items():
        assert isinstance(cmds, list), f"{group} commands should be a list"
        for cmd in cmds:
            assert isinstance(cmd, str) and cmd, f"Empty/non-string command in group {group}"


def test_all_group_names_in_command_groups() -> None:
    for name in ALL_GROUP_NAMES:
        assert name in COMMAND_GROUPS


# ---------------------------------------------------------------------------
# CollectionProfile enum values
# ---------------------------------------------------------------------------


def test_profile_enum_values() -> None:
    assert CollectionProfile.MINIMAL == "minimal"
    assert CollectionProfile.STANDARD == "standard"
    assert CollectionProfile.FULL == "full"
    assert CollectionProfile.CUSTOM == "custom"
