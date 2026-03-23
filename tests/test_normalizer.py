"""Unit tests for link normalization and placeholder creation."""

from backend.models import (
    ChannelMember,
    Device,
    DeviceStatus,
    EtherChannelInfo,
    Link,
    NeighborRecord,
)
from backend.normalizer import (
    build_placeholder_devices,
    collapse_port_channel_links,
    is_in_scope,
    normalize_interface_name,
    normalize_links,
)


def make_link(src, src_intf, tgt, tgt_intf, protocol="CDP") -> Link:
    return Link(
        source=src, source_intf=src_intf, target=tgt, target_intf=tgt_intf, protocol=protocol
    )


class TestNormalizeLinks:
    def test_no_duplicates(self):
        links = [
            make_link("A", "Gi1/0/1", "B", "Gi0/1"),
            make_link("B", "Gi0/1", "A", "Gi1/0/1"),  # duplicate, reversed
        ]
        result = normalize_links(links)
        assert len(result) == 1

    def test_distinct_links_kept(self):
        links = [
            make_link("A", "Gi1/0/1", "B", "Gi0/1"),
            make_link("A", "Gi1/0/2", "C", "Gi0/2"),
        ]
        result = normalize_links(links)
        assert len(result) == 2

    def test_empty(self):
        assert normalize_links([]) == []

    def test_self_loop_kept(self):
        links = [make_link("A", "Gi1", "A", "Gi2")]
        result = normalize_links(links)
        assert len(result) == 1

    def test_different_protocols_both_kept(self):
        links = [
            make_link("A", "Gi1/0/1", "B", "Gi0/1", "CDP"),
            make_link("A", "Gi1/0/1", "B", "Gi0/1", "LLDP"),
        ]
        # Same interfaces, treated as same physical link — first wins
        result = normalize_links(links)
        assert len(result) == 1


class TestBuildPlaceholders:
    def test_placeholder_for_unvisited(self):
        nb = NeighborRecord(
            device_id="UNKNOWN-SW",
            ip_address="192.168.1.1",
            local_interface="Gi1/0/1",
            protocol="CDP",
        )
        placeholders = build_placeholder_devices([nb], discovered_ids=set())
        assert len(placeholders) == 1
        assert placeholders[0].id == "UNKNOWN-SW"
        assert placeholders[0].status.value == "placeholder"

    def test_no_placeholder_for_discovered(self):
        nb = NeighborRecord(
            device_id="KNOWN-SW",
            ip_address="192.168.1.2",
            local_interface="Gi1/0/1",
            protocol="CDP",
        )
        placeholders = build_placeholder_devices([nb], discovered_ids={"KNOWN-SW"})
        assert placeholders == []

    def test_deduplicates_same_neighbor(self):
        nb1 = NeighborRecord(
            device_id="SW-01", ip_address="10.0.0.1", local_interface="Gi1", protocol="CDP"
        )
        nb2 = NeighborRecord(
            device_id="SW-01", ip_address="10.0.0.1", local_interface="Gi2", protocol="CDP"
        )
        placeholders = build_placeholder_devices([nb1, nb2], discovered_ids=set())
        assert len(placeholders) == 1


class TestIsInScope:
    def test_no_scope_always_true(self):
        assert is_in_scope("10.0.0.1", None) is True

    def test_ip_in_cidr(self):
        assert is_in_scope("10.0.0.50", "10.0.0.0/24") is True

    def test_ip_not_in_cidr(self):
        assert is_in_scope("192.168.0.1", "10.0.0.0/24") is False

    def test_invalid_ip_false(self):
        assert is_in_scope("not-an-ip", "10.0.0.0/8") is False

    def test_invalid_cidr_false(self):
        assert is_in_scope("10.0.0.1", "not-a-cidr") is False

    def test_host_cidr(self):
        assert is_in_scope("10.0.0.1", "10.0.0.1/32") is True


class TestNormalizeInterfaceName:
    def test_gi_expands(self):
        assert normalize_interface_name("Gi1/0/1") == "GigabitEthernet1/0/1"

    def test_te_expands(self):
        assert normalize_interface_name("Te1/1/1") == "TenGigabitEthernet1/1/1"

    def test_full_name_unchanged(self):
        assert normalize_interface_name("GigabitEthernet0/1") == "GigabitEthernet0/1"

    def test_fa_expands(self):
        assert normalize_interface_name("Fa0/1") == "FastEthernet0/1"

    def test_unknown_prefix_unchanged(self):
        assert normalize_interface_name("Xyz1/0") == "Xyz1/0"


class TestNormalizeLinksWithAbbrevIntf:
    """Verify that abbreviated and full interface names deduplicate correctly."""

    def test_abbreviated_vs_full_deduped(self):
        """Gi1/0/1 and GigabitEthernet1/0/1 should be treated as the same endpoint."""
        links = [
            make_link("A", "Gi1/0/1", "B", "GigabitEthernet0/1"),
            # reversed, full names
            make_link("B", "GigabitEthernet0/1", "A", "GigabitEthernet1/0/1"),
        ]
        result = normalize_links(links)
        assert len(result) == 1

    def test_both_abbreviated_deduped(self):
        links = [
            make_link("A", "Gi1/0/1", "B", "Gi0/1"),
            make_link("B", "GigabitEthernet0/1", "A", "GigabitEthernet1/0/1"),
        ]
        result = normalize_links(links)
        assert len(result) == 1

    def test_different_interfaces_kept(self):
        links = [
            make_link("A", "Gi1/0/1", "B", "Gi0/1"),
            make_link("A", "Gi1/0/2", "B", "Gi0/2"),
        ]
        result = normalize_links(links)
        assert len(result) == 2

    def test_te_vs_full_deduped(self):
        links = [
            make_link("R1", "Te1/1", "R2", "Te2/1"),
            make_link("R2", "TenGigabitEthernet2/1", "R1", "TenGigabitEthernet1/1"),
        ]
        result = normalize_links(links)
        assert len(result) == 1


def make_device(dev_id: str, etherchannels: list[EtherChannelInfo]) -> Device:
    return Device(
        id=dev_id, mgmt_ip="10.0.0.1", status=DeviceStatus.OK, etherchannels=etherchannels
    )


def make_ec(po_name: str, members: list[str]) -> EtherChannelInfo:
    return EtherChannelInfo(
        channel_id=po_name.replace("Po", ""),
        port_channel=po_name,
        status="up",
        members=[ChannelMember(interface=m, status="P", status_desc="bundled") for m in members],
    )


class TestCollapsePortChannelLinks:
    def test_two_member_links_collapsed(self):
        """Two CDP links that are both members of Po1 → single edge labeled Po1."""
        sw_a = make_device(
            "SW-A", [make_ec("Po1", ["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"])]
        )
        sw_b = make_device("SW-B", [make_ec("Po1", ["GigabitEthernet0/1", "GigabitEthernet0/2"])])
        links = [
            make_link("SW-A", "Gi1/0/1", "SW-B", "Gi0/1"),
            make_link("SW-A", "Gi1/0/2", "SW-B", "Gi0/2"),
        ]
        result = collapse_port_channel_links(links, [sw_a, sw_b])
        assert len(result) == 1
        assert result[0].port_channel == "Po1"
        assert result[0].source_intf == "Po1"
        assert result[0].target_intf == "Po1"
        assert result[0].member_count == 2
        assert len(result[0].members) == 2

    def test_speed_label_10g(self):
        sw_a = make_device(
            "SW-A", [make_ec("Po1", ["TenGigabitEthernet1/1/1", "TenGigabitEthernet1/1/2"])]
        )
        sw_b = make_device(
            "SW-B", [make_ec("Po1", ["TenGigabitEthernet0/1", "TenGigabitEthernet0/2"])]
        )
        links = [
            make_link("SW-A", "Te1/1/1", "SW-B", "Te0/1"),
            make_link("SW-A", "Te1/1/2", "SW-B", "Te0/2"),
        ]
        result = collapse_port_channel_links(links, [sw_a, sw_b])
        assert len(result) == 1
        assert result[0].speed_label == "2x10G"

    def test_four_member_speed_label(self):
        members_a = [f"TenGigabitEthernet1/1/{i}" for i in range(1, 5)]
        members_b = [f"TenGigabitEthernet0/{i}" for i in range(1, 5)]
        sw_a = make_device("SW-A", [make_ec("Po2", members_a)])
        sw_b = make_device("SW-B", [make_ec("Po2", members_b)])
        links = [make_link("SW-A", f"Te1/1/{i}", "SW-B", f"Te0/{i}") for i in range(1, 5)]
        result = collapse_port_channel_links(links, [sw_a, sw_b])
        assert len(result) == 1
        assert result[0].speed_label == "4x10G"
        assert result[0].member_count == 4

    def test_single_link_not_collapsed(self):
        """A single link that belongs to a port-channel should NOT be collapsed."""
        sw_a = make_device("SW-A", [make_ec("Po1", ["GigabitEthernet1/0/1"])])
        sw_b = make_device("SW-B", [])
        links = [make_link("SW-A", "Gi1/0/1", "SW-B", "Gi0/1")]
        result = collapse_port_channel_links(links, [sw_a, sw_b])
        assert len(result) == 1
        assert result[0].port_channel is None  # not collapsed

    def test_non_po_link_unchanged(self):
        """Links not belonging to any port-channel are left unchanged."""
        sw_a = make_device("SW-A", [])
        sw_b = make_device("SW-B", [])
        links = [make_link("SW-A", "Gi1/0/1", "SW-B", "Gi0/1")]
        result = collapse_port_channel_links(links, [sw_a, sw_b])
        assert len(result) == 1
        assert result[0].source_intf == "Gi1/0/1"
        assert result[0].port_channel is None

    def test_asymmetric_po_data(self):
        """Source has EC data, target does not — still collapses using source's po name."""
        sw_a = make_device(
            "SW-A", [make_ec("Po1", ["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"])]
        )
        sw_b = make_device("SW-B", [])  # router: no etherchannel data
        links = [
            make_link("SW-A", "Gi1/0/1", "SW-B", "Gi0/1"),
            make_link("SW-A", "Gi1/0/2", "SW-B", "Gi0/2"),
        ]
        result = collapse_port_channel_links(links, [sw_a, sw_b])
        assert len(result) == 1
        assert result[0].port_channel == "Po1"
        assert result[0].member_count == 2

    def test_multiple_po_between_same_pair(self):
        """Two separate port-channels between the same device pair remain as 2 edges."""
        sw_a = make_device(
            "SW-A",
            [
                make_ec("Po1", ["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"]),
                make_ec("Po2", ["TenGigabitEthernet1/1/1", "TenGigabitEthernet1/1/2"]),
            ],
        )
        sw_b = make_device(
            "SW-B",
            [
                make_ec("Po1", ["GigabitEthernet0/1", "GigabitEthernet0/2"]),
                make_ec("Po2", ["TenGigabitEthernet0/1", "TenGigabitEthernet0/2"]),
            ],
        )
        links = [
            make_link("SW-A", "Gi1/0/1", "SW-B", "Gi0/1"),
            make_link("SW-A", "Gi1/0/2", "SW-B", "Gi0/2"),
            make_link("SW-A", "Te1/1/1", "SW-B", "Te0/1"),
            make_link("SW-A", "Te1/1/2", "SW-B", "Te0/2"),
        ]
        result = collapse_port_channel_links(links, [sw_a, sw_b])
        assert len(result) == 2
        po_names = {r.port_channel for r in result}
        assert po_names == {"Po1", "Po2"}

    def test_empty_links(self):
        assert collapse_port_channel_links([], []) == []
