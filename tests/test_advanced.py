"""Unit tests for Advanced Mode — command generation, rollback, audit store, and guardrails."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.advanced import (
    _check_trunk_or_channel,
    _extract_current_vlan,
    _intf_matches,
    _validate_interface,
    generate_rollback_commands,
    generate_vlan_commands,
)
from backend.audit_store import AuditStore
from backend.models import AdvancedStatus, AuditRecord, PortChange

# ---------------------------------------------------------------------------
# Command generation
# ---------------------------------------------------------------------------


class TestGenerateVlanCommands:
    def test_single_interface(self) -> None:
        cmds = generate_vlan_commands(["GigabitEthernet1/0/1"], 10)
        assert cmds == [
            "interface GigabitEthernet1/0/1",
            "switchport access vlan 10",
        ]

    def test_multiple_interfaces(self) -> None:
        cmds = generate_vlan_commands(["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"], 20)
        assert len(cmds) == 4
        assert cmds[0] == "interface GigabitEthernet1/0/1"
        assert cmds[1] == "switchport access vlan 20"
        assert cmds[2] == "interface GigabitEthernet1/0/2"
        assert cmds[3] == "switchport access vlan 20"

    def test_with_description(self) -> None:
        cmds = generate_vlan_commands(["GigabitEthernet1/0/1"], 10, description="User PC")
        assert "description User PC" in cmds

    def test_write_mem_iosxe(self) -> None:
        cmds = generate_vlan_commands(
            ["GigabitEthernet1/0/1"], 10, write_mem=True, platform="iosxe"
        )
        assert cmds[-1] == "write memory"

    def test_write_mem_nxos(self) -> None:
        cmds = generate_vlan_commands(["GigabitEthernet1/0/1"], 10, write_mem=True, platform="nxos")
        assert cmds[-1] == "copy running-config startup-config"

    def test_no_write_mem(self) -> None:
        cmds = generate_vlan_commands(["GigabitEthernet1/0/1"], 10, write_mem=False)
        assert "write memory" not in cmds
        assert "copy running-config startup-config" not in cmds


class TestGenerateRollbackCommands:
    def test_rollback_with_vlan(self) -> None:
        pre = {"GigabitEthernet1/0/1": "switchport access vlan 10\ndescription Old Port"}
        cmds = generate_rollback_commands(pre)
        assert "interface GigabitEthernet1/0/1" in cmds
        assert "switchport access vlan 10" in cmds
        assert "description Old Port" in cmds

    def test_rollback_no_vlan(self) -> None:
        pre = {"GigabitEthernet1/0/1": "switchport mode access\n"}
        cmds = generate_rollback_commands(pre)
        assert "no switchport access vlan" in cmds

    def test_rollback_no_description(self) -> None:
        pre = {"GigabitEthernet1/0/1": "switchport access vlan 10\n"}
        cmds = generate_rollback_commands(pre)
        assert "no description" in cmds

    def test_rollback_write_mem_iosxe(self) -> None:
        pre = {"GigabitEthernet1/0/1": "switchport access vlan 10"}
        cmds = generate_rollback_commands(pre, write_mem=True, platform="iosxe")
        assert cmds[-1] == "write memory"

    def test_rollback_write_mem_nxos(self) -> None:
        pre = {"GigabitEthernet1/0/1": "switchport access vlan 10"}
        cmds = generate_rollback_commands(pre, write_mem=True, platform="nxos")
        assert cmds[-1] == "copy running-config startup-config"


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


class TestGuardrails:
    def test_protected_vlan_interface(self) -> None:
        assert _validate_interface("Vlan10") is not None
        assert _validate_interface("vlan1") is not None

    def test_protected_loopback(self) -> None:
        assert _validate_interface("Loopback0") is not None
        assert _validate_interface("lo0") is not None

    def test_protected_mgmt(self) -> None:
        assert _validate_interface("mgmt0") is not None
        assert _validate_interface("Management0") is not None

    def test_protected_port_channel(self) -> None:
        assert _validate_interface("Port-channel1") is not None
        assert _validate_interface("Po1") is not None

    def test_protected_nve(self) -> None:
        assert _validate_interface("nve1") is not None

    def test_protected_tunnel(self) -> None:
        assert _validate_interface("Tunnel0") is not None

    def test_allowed_gigabit(self) -> None:
        assert _validate_interface("GigabitEthernet1/0/1") is None

    def test_allowed_ethernet(self) -> None:
        assert _validate_interface("Ethernet1/1") is None

    def test_allowed_fastethernet(self) -> None:
        assert _validate_interface("FastEthernet0/1") is None

    def test_trunk_detected(self) -> None:
        config = "interface Gi1/0/1\n switchport mode trunk\n switchport trunk allowed vlan 10,20"
        assert _check_trunk_or_channel(config, "Gi1/0/1") is not None

    def test_channel_group_detected(self) -> None:
        config = "interface Gi1/0/1\n channel-group 1 mode active"
        assert _check_trunk_or_channel(config, "Gi1/0/1") is not None

    def test_access_port_ok(self) -> None:
        config = "interface Gi1/0/1\n switchport mode access\n switchport access vlan 10"
        assert _check_trunk_or_channel(config, "Gi1/0/1") is None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_extract_current_vlan(self) -> None:
        config = "switchport access vlan 10\nswitchport mode access"
        assert _extract_current_vlan(config) == "10"

    def test_extract_no_vlan(self) -> None:
        config = "switchport mode access\n"
        assert _extract_current_vlan(config) is None

    def test_intf_matches_exact(self) -> None:
        assert _intf_matches("GigabitEthernet1/0/1", "GigabitEthernet1/0/1")

    def test_intf_matches_abbrev(self) -> None:
        assert _intf_matches("Gi1/0/1", "GigabitEthernet1/0/1")

    def test_intf_matches_reverse(self) -> None:
        assert _intf_matches("GigabitEthernet1/0/1", "Gi1/0/1")

    def test_intf_no_match(self) -> None:
        assert not _intf_matches("Gi1/0/1", "Gi1/0/2")


# ---------------------------------------------------------------------------
# Audit store (in-memory)
# ---------------------------------------------------------------------------


def _make_record(
    audit_id: str = "rec-1",
    device_id: str = "SW-01",
    status: AdvancedStatus = AdvancedStatus.SUCCESS,
    interfaces: list[str] | None = None,
) -> AuditRecord:
    changes = []
    for intf in interfaces or ["GigabitEthernet1/0/1"]:
        changes.append(
            PortChange(
                interface=intf,
                field="access_vlan",
                old_value="10",
                new_value="20",
                verified=True,
            )
        )
    return AuditRecord(
        id=audit_id,
        timestamp=datetime.now(UTC),
        device_id=device_id,
        device_ip="10.0.0.1",
        platform="iosxe",
        operation="vlan_change",
        status=status,
        changes=changes,
        commands_sent=["interface GigabitEthernet1/0/1", "switchport access vlan 20"],
        pre_state={"GigabitEthernet1/0/1": "switchport access vlan 10"},
        post_state={"GigabitEthernet1/0/1": "switchport access vlan 20"},
        rollback_commands=[
            "interface GigabitEthernet1/0/1",
            "switchport access vlan 10",
        ],
    )


class TestAuditStore:
    @pytest.fixture
    def store(self) -> AuditStore:
        return AuditStore()

    async def test_create_and_get(self, store: AuditStore) -> None:
        record = _make_record()
        await store.create(record)
        found = store.get("rec-1")
        assert found is not None
        assert found.id == "rec-1"

    async def test_get_not_found(self, store: AuditStore) -> None:
        assert store.get("nonexistent") is None

    async def test_list_all(self, store: AuditStore) -> None:
        await store.create(_make_record("r1"))
        await store.create(_make_record("r2"))
        records = store.list_all()
        assert len(records) == 2

    async def test_list_filter_device(self, store: AuditStore) -> None:
        await store.create(_make_record("r1", device_id="SW-01"))
        await store.create(_make_record("r2", device_id="SW-02"))
        records = store.list_all(device_id="SW-01")
        assert len(records) == 1
        assert records[0].device_id == "SW-01"

    async def test_list_pagination(self, store: AuditStore) -> None:
        for i in range(5):
            await store.create(_make_record(f"r{i}"))
        page = store.list_all(limit=2, offset=0)
        assert len(page) == 2
        page2 = store.list_all(limit=2, offset=2)
        assert len(page2) == 2

    async def test_mark_rolled_back(self, store: AuditStore) -> None:
        await store.create(_make_record("r1"))
        result = await store.mark_rolled_back("r1", "undo-1")
        assert result is True
        updated = store.get("r1")
        assert updated is not None
        assert updated.undone_by == "undo-1"

    async def test_mark_rolled_back_not_found(self, store: AuditStore) -> None:
        result = await store.mark_rolled_back("nonexistent", "undo-1")
        assert result is False

    async def test_check_conflicts(self, store: AuditStore) -> None:
        await store.create(_make_record("r1", interfaces=["GigabitEthernet1/0/1"]))
        conflicts = store.check_conflicts("SW-01", ["GigabitEthernet1/0/1"])
        assert len(conflicts) == 1

    async def test_check_conflicts_no_overlap(self, store: AuditStore) -> None:
        await store.create(_make_record("r1", interfaces=["GigabitEthernet1/0/1"]))
        conflicts = store.check_conflicts("SW-01", ["GigabitEthernet1/0/2"])
        assert len(conflicts) == 0

    async def test_export_csv(self, store: AuditStore) -> None:
        await store.create(_make_record("r1"))
        csv_data = store.export_csv()
        assert "r1" in csv_data
        assert "SW-01" in csv_data
        lines = csv_data.strip().split("\n")
        assert len(lines) == 2  # header + 1 record

    async def test_export_json(self, store: AuditStore) -> None:
        await store.create(_make_record("r1"))
        json_data = store.export_json()
        assert "r1" in json_data
        assert "SW-01" in json_data

    async def test_cleanup(self, store: AuditStore) -> None:
        # Create a record with old timestamp
        old_record = _make_record("old")
        old_record = old_record.model_copy(update={"timestamp": datetime(2020, 1, 1, tzinfo=UTC)})
        await store.create(old_record)
        await store.create(_make_record("new"))
        deleted = await store.cleanup(retention_days=30)
        assert deleted == 1
        assert store.get("old") is None
        assert store.get("new") is not None

    async def test_cleanup_zero_retention(self, store: AuditStore) -> None:
        await store.create(_make_record("r1"))
        deleted = await store.cleanup(retention_days=0)
        assert deleted == 0
