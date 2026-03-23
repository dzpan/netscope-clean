"""Tests for the Configuration Playbook system.

Covers:
- Variable interpolation engine
- Command safety validation
- Variable validation and resolution
- Playbook model construction
- PlaybookStore (in-memory) CRUD
- Dry-run logic
- API endpoint contracts (via TestClient)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.playbook_store import PlaybookStore
from backend.playbooks import (
    _INTERFACE_PATTERN,
    _MAX_VARIABLE_VALUE_LENGTH,
    ConfigMode,
    DeviceExecutionResult,
    ExecutionStatus,
    Platform,
    Playbook,
    PlaybookCategory,
    PlaybookCreateRequest,
    PlaybookExecuteRequest,
    PlaybookExecution,
    PlaybookVariable,
    VariableType,
    interpolate,
    interpolate_commands,
    resolve_variables,
    validate_command_safety,
    validate_variables,
)

# ---------------------------------------------------------------------------
# Interpolation tests
# ---------------------------------------------------------------------------


class TestInterpolation:
    def test_simple_substitution(self) -> None:
        result = interpolate("interface {{interface}}", {"interface": "Gi1/0/1"})
        assert result == "interface Gi1/0/1"

    def test_multiple_variables(self) -> None:
        result = interpolate(
            "switchport access vlan {{vlan_id}} ! {{description}}",
            {"vlan_id": "100", "description": "server-port"},
        )
        assert result == "switchport access vlan 100 ! server-port"

    def test_whitespace_in_braces(self) -> None:
        result = interpolate("vlan {{ vlan_id }}", {"vlan_id": "200"})
        assert result == "vlan 200"

    def test_missing_variable_raises(self) -> None:
        with pytest.raises(ValueError, match="not provided"):
            interpolate("interface {{interface}}", {})

    def test_no_variables_passthrough(self) -> None:
        result = interpolate("show version", {})
        assert result == "show version"

    def test_interpolate_commands_list(self) -> None:
        cmds = ["interface {{intf}}", "switchport access vlan {{vlan}}"]
        result = interpolate_commands(cmds, {"intf": "Gi1/0/1", "vlan": "10"})
        assert result == ["interface Gi1/0/1", "switchport access vlan 10"]

    def test_repeated_variable(self) -> None:
        result = interpolate("{{server}} and {{server}}", {"server": "10.0.0.1"})
        assert result == "10.0.0.1 and 10.0.0.1"

    def test_optional_variable_with_value(self) -> None:
        result = interpolate("description {{?desc}}", {"desc": "uplink"})
        assert result == "description uplink"

    def test_optional_variable_empty_skips(self) -> None:
        from backend.playbooks import _SkipCommand

        with pytest.raises(_SkipCommand):
            interpolate("description {{?desc}}", {"desc": ""})

    def test_optional_variable_missing_skips(self) -> None:
        from backend.playbooks import _SkipCommand

        with pytest.raises(_SkipCommand):
            interpolate("description {{?desc}}", {})

    def test_interpolate_commands_skips_optional_empty(self) -> None:
        cmds = [
            "interface {{intf}}",
            "description {{?desc}}",
            "no shutdown",
        ]
        result = interpolate_commands(cmds, {"intf": "Gi1/0/1", "desc": ""})
        assert result == ["interface Gi1/0/1", "no shutdown"]

    def test_interpolate_commands_keeps_optional_with_value(self) -> None:
        cmds = [
            "interface {{intf}}",
            "description {{?desc}}",
            "no shutdown",
        ]
        result = interpolate_commands(cmds, {"intf": "Gi1/0/1", "desc": "uplink"})
        assert result == ["interface Gi1/0/1", "description uplink", "no shutdown"]


# ---------------------------------------------------------------------------
# Variable validation tests
# ---------------------------------------------------------------------------


class TestVariableValidation:
    def _make_playbook(self, variables: list[PlaybookVariable]) -> Playbook:
        return Playbook(
            title="Test",
            variables=variables,
            steps=["show version"],
        )

    def test_required_missing(self) -> None:
        pb = self._make_playbook(
            [
                PlaybookVariable(name="vlan_id", var_type=VariableType.INT, required=True),
            ]
        )
        errors = validate_variables(pb, {})
        assert any("missing" in e.lower() for e in errors)

    def test_required_with_default_ok(self) -> None:
        pb = self._make_playbook(
            [
                PlaybookVariable(
                    name="vlan_id", var_type=VariableType.INT, required=True, default="100"
                ),
            ]
        )
        errors = validate_variables(pb, {})
        assert len(errors) == 0

    def test_int_validation(self) -> None:
        pb = self._make_playbook(
            [
                PlaybookVariable(name="count", var_type=VariableType.INT),
            ]
        )
        errors = validate_variables(pb, {"count": "abc"})
        assert any("integer" in e.lower() for e in errors)

    def test_int_valid(self) -> None:
        pb = self._make_playbook(
            [
                PlaybookVariable(name="count", var_type=VariableType.INT),
            ]
        )
        errors = validate_variables(pb, {"count": "42"})
        assert len(errors) == 0

    def test_choice_validation(self) -> None:
        pb = self._make_playbook(
            [
                PlaybookVariable(
                    name="action",
                    var_type=VariableType.CHOICE,
                    choices=["shutdown", "no shutdown"],
                ),
            ]
        )
        errors = validate_variables(pb, {"action": "destroy"})
        assert any("one of" in e.lower() for e in errors)

    def test_choice_valid(self) -> None:
        pb = self._make_playbook(
            [
                PlaybookVariable(
                    name="action",
                    var_type=VariableType.CHOICE,
                    choices=["shutdown", "no shutdown"],
                ),
            ]
        )
        errors = validate_variables(pb, {"action": "shutdown"})
        assert len(errors) == 0

    def test_unknown_variable(self) -> None:
        pb = self._make_playbook([])
        errors = validate_variables(pb, {"mystery": "value"})
        assert any("unknown" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Variable resolution tests
# ---------------------------------------------------------------------------


class TestVariableResolution:
    def test_defaults_applied(self) -> None:
        pb = Playbook(
            title="Test",
            variables=[
                PlaybookVariable(name="vlan", var_type=VariableType.INT, default="100"),
                PlaybookVariable(name="intf", var_type=VariableType.INTERFACE),
            ],
            steps=["show version"],
        )
        resolved = resolve_variables(pb, {"intf": "Gi1/0/1"})
        assert resolved == {"vlan": "100", "intf": "Gi1/0/1"}

    def test_provided_overrides_default(self) -> None:
        pb = Playbook(
            title="Test",
            variables=[
                PlaybookVariable(name="vlan", var_type=VariableType.INT, default="100"),
            ],
            steps=["show version"],
        )
        resolved = resolve_variables(pb, {"vlan": "200"})
        assert resolved == {"vlan": "200"}


# ---------------------------------------------------------------------------
# Command safety tests
# ---------------------------------------------------------------------------


class TestCommandSafety:
    def test_safe_commands(self) -> None:
        errors = validate_command_safety(
            [
                "interface Gi1/0/1",
                "switchport access vlan 100",
                "no shutdown",
                "show running-config",
            ]
        )
        assert len(errors) == 0

    def test_blocked_erase(self) -> None:
        errors = validate_command_safety(["erase startup-config"])
        assert len(errors) == 1
        assert "erase" in errors[0].lower()

    def test_blocked_reload(self) -> None:
        errors = validate_command_safety(["reload"])
        assert len(errors) == 1

    def test_blocked_write_erase(self) -> None:
        errors = validate_command_safety(["write erase"])
        assert len(errors) == 1

    def test_blocked_delete(self) -> None:
        errors = validate_command_safety(["delete flash:startup-config"])
        assert len(errors) == 1

    def test_blocked_format(self) -> None:
        errors = validate_command_safety(["format flash:"])
        assert len(errors) == 1

    def test_multiple_blocked(self) -> None:
        errors = validate_command_safety(["erase startup-config", "reload", "show version"])
        assert len(errors) == 2


# ---------------------------------------------------------------------------
# PlaybookStore (in-memory) tests
# ---------------------------------------------------------------------------


class TestPlaybookStore:
    @pytest.fixture
    def store(self) -> PlaybookStore:
        return PlaybookStore()

    @pytest.fixture
    def sample_playbook(self) -> Playbook:
        return Playbook(
            id="test-1",
            title="Test Playbook",
            description="A test playbook",
            category=PlaybookCategory.VLAN,
            platforms=[Platform.IOSXE],
            variables=[
                PlaybookVariable(name="vlan_id", var_type=VariableType.INT, required=True),
            ],
            steps=["interface {{interface}}", "switchport access vlan {{vlan_id}}"],
            created_at=datetime.now(UTC),
        )

    async def test_save_and_get(self, store: PlaybookStore, sample_playbook: Playbook) -> None:
        await store.save_playbook(sample_playbook)
        retrieved = store.get_playbook("test-1")
        assert retrieved is not None
        assert retrieved.title == "Test Playbook"

    async def test_get_missing(self, store: PlaybookStore) -> None:
        assert store.get_playbook("nonexistent") is None

    async def test_list_all(self, store: PlaybookStore, sample_playbook: Playbook) -> None:
        await store.save_playbook(sample_playbook)
        result = store.list_playbooks()
        assert len(result) == 1

    async def test_list_by_category(self, store: PlaybookStore, sample_playbook: Playbook) -> None:
        await store.save_playbook(sample_playbook)
        result = store.list_playbooks(category="vlan")
        assert len(result) == 1
        result = store.list_playbooks(category="security")
        assert len(result) == 0

    async def test_list_search(self, store: PlaybookStore, sample_playbook: Playbook) -> None:
        await store.save_playbook(sample_playbook)
        result = store.list_playbooks(search="test")
        assert len(result) == 1
        result = store.list_playbooks(search="nonexistent")
        assert len(result) == 0

    async def test_delete(self, store: PlaybookStore, sample_playbook: Playbook) -> None:
        await store.save_playbook(sample_playbook)
        deleted = await store.delete_playbook("test-1")
        assert deleted is True
        assert store.get_playbook("test-1") is None

    async def test_delete_missing(self, store: PlaybookStore) -> None:
        deleted = await store.delete_playbook("nonexistent")
        assert deleted is False

    async def test_cannot_delete_builtin(self, store: PlaybookStore) -> None:
        builtin = Playbook(
            id="builtin-1",
            title="Built-in",
            steps=["show version"],
            builtin=True,
            created_at=datetime.now(UTC),
        )
        await store.save_playbook(builtin)
        deleted = await store.delete_playbook("builtin-1")
        assert deleted is False
        assert store.get_playbook("builtin-1") is not None


# ---------------------------------------------------------------------------
# Playbook model validation tests
# ---------------------------------------------------------------------------


class TestPlaybookModel:
    def test_variable_name_must_be_identifier(self) -> None:
        with pytest.raises(Exception):
            PlaybookVariable(name="invalid-name", var_type=VariableType.STRING)

    def test_variable_name_valid(self) -> None:
        v = PlaybookVariable(name="valid_name", var_type=VariableType.STRING)
        assert v.name == "valid_name"

    def test_playbook_requires_steps(self) -> None:
        with pytest.raises(Exception):
            Playbook(title="No steps", steps=[])

    def test_playbook_create_request(self) -> None:
        req = PlaybookCreateRequest(
            title="Test",
            steps=["show version"],
        )
        assert req.title == "Test"


# ---------------------------------------------------------------------------
# Dry-run tests
# ---------------------------------------------------------------------------


class TestDryRun:
    async def test_dry_run_success(self) -> None:
        from backend.playbook_engine import dry_run

        pb = Playbook(
            title="Test",
            variables=[
                PlaybookVariable(name="intf", var_type=VariableType.INTERFACE, required=True),
                PlaybookVariable(name="vlan", var_type=VariableType.INT, required=True),
            ],
            pre_checks=["show running-config interface {{intf}}"],
            steps=["interface {{intf}}", "switchport access vlan {{vlan}}"],
            post_checks=["show interfaces {{intf}} status"],
        )
        result = await dry_run(pb, {"intf": "Gi1/0/1", "vlan": "100"})
        assert result["errors"] == []
        assert result["pre_checks"] == ["show running-config interface Gi1/0/1"]
        assert result["steps"] == ["interface Gi1/0/1", "switchport access vlan 100"]
        assert result["post_checks"] == ["show interfaces Gi1/0/1 status"]

    async def test_dry_run_missing_variable(self) -> None:
        from backend.playbook_engine import dry_run

        pb = Playbook(
            title="Test",
            variables=[
                PlaybookVariable(name="intf", var_type=VariableType.INTERFACE, required=True),
            ],
            steps=["interface {{intf}}"],
        )
        result = await dry_run(pb, {})
        assert len(result["errors"]) > 0

    async def test_dry_run_blocked_command(self) -> None:
        from backend.playbook_engine import dry_run

        pb = Playbook(
            title="Test",
            steps=["erase startup-config"],
        )
        result = await dry_run(pb, {})
        assert any("blocked" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# API endpoint tests (via httpx TestClient)
# ---------------------------------------------------------------------------


class TestPlaybookAPI:
    @pytest.fixture
    def client(self):  # type: ignore[no-untyped-def]
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test/api/v1")

    async def test_list_playbooks(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/playbooks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_create_and_get_playbook(self, client) -> None:  # type: ignore[no-untyped-def]
        create_resp = await client.post(
            "/playbooks",
            json={
                "title": "API Test Playbook",
                "steps": ["show version"],
                "description": "Created via test",
            },
        )
        assert create_resp.status_code == 201
        pb = create_resp.json()
        assert pb["title"] == "API Test Playbook"
        pb_id = pb["id"]

        get_resp = await client.get(f"/playbooks/{pb_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "API Test Playbook"

    async def test_update_playbook(self, client) -> None:  # type: ignore[no-untyped-def]
        create_resp = await client.post(
            "/playbooks",
            json={"title": "Before Update", "steps": ["show version"]},
        )
        pb_id = create_resp.json()["id"]

        update_resp = await client.put(
            f"/playbooks/{pb_id}",
            json={"title": "After Update"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["title"] == "After Update"

    async def test_delete_playbook(self, client) -> None:  # type: ignore[no-untyped-def]
        create_resp = await client.post(
            "/playbooks",
            json={"title": "To Delete", "steps": ["show version"]},
        )
        pb_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/playbooks/{pb_id}")
        assert del_resp.status_code == 204

        get_resp = await client.get(f"/playbooks/{pb_id}")
        assert get_resp.status_code == 404

    async def test_dry_run_endpoint(self, client) -> None:  # type: ignore[no-untyped-def]
        create_resp = await client.post(
            "/playbooks",
            json={
                "title": "Dry Run Test",
                "variables": [
                    {"name": "intf", "var_type": "interface", "required": True},
                ],
                "steps": ["interface {{intf}}", "no shutdown"],
                "pre_checks": ["show interfaces {{intf}} status"],
            },
        )
        pb_id = create_resp.json()["id"]

        dr_resp = await client.post(
            f"/playbooks/{pb_id}/dry-run",
            json={"variables": {"intf": "Gi1/0/1"}},
        )
        assert dr_resp.status_code == 200
        data = dr_resp.json()
        assert data["errors"] == []
        assert data["steps"] == ["interface Gi1/0/1", "no shutdown"]

    async def test_get_nonexistent_playbook(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/playbooks/does-not-exist")
        assert resp.status_code == 404

    async def test_list_playbook_runs_empty(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/playbook-runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_export_playbook(self, client) -> None:  # type: ignore[no-untyped-def]
        create_resp = await client.post(
            "/playbooks",
            json={
                "title": "Export Test",
                "description": "For export",
                "category": "vlan",
                "steps": ["show version"],
            },
        )
        pb_id = create_resp.json()["id"]

        export_resp = await client.get(f"/playbooks/{pb_id}/export")
        assert export_resp.status_code == 200
        data = export_resp.json()
        assert data["name"] == "Export Test"
        assert data["category"] == "vlan"

    async def test_import_playbook(self, client) -> None:  # type: ignore[no-untyped-def]
        import_resp = await client.post(
            "/playbooks/import",
            json={
                "name": "Imported Playbook",
                "description": "Imported via API",
                "category": "security",
                "platform": ["iosxe"],
                "variables": [
                    {"name": "server", "type": "string", "required": True},
                ],
                "steps": ["logging host {{server}}"],
                "pre_checks": ["show logging"],
                "post_checks": ["show logging"],
                "rollback": ["no logging host {{server}}"],
            },
        )
        assert import_resp.status_code == 201
        data = import_resp.json()
        assert data["title"] == "Imported Playbook"
        assert data["category"] == "security"


# ---------------------------------------------------------------------------
# Variable injection prevention tests (NET-62)
# ---------------------------------------------------------------------------


class TestVariableInjectionPrevention:
    """Ensure variable values with control characters are rejected."""

    def test_newline_in_value_rejected_by_interpolate(self) -> None:
        with pytest.raises(ValueError, match="control characters"):
            interpolate("logging host {{server}}", {"server": "10.0.0.1\nshutdown"})

    def test_carriage_return_rejected(self) -> None:
        with pytest.raises(ValueError, match="control characters"):
            interpolate("desc {{desc}}", {"desc": "port\rshutdown"})

    def test_tab_rejected(self) -> None:
        with pytest.raises(ValueError, match="control characters"):
            interpolate("desc {{desc}}", {"desc": "port\tinfo"})

    def test_null_byte_rejected(self) -> None:
        with pytest.raises(ValueError, match="control characters"):
            interpolate("desc {{desc}}", {"desc": "port\x00info"})

    def test_max_length_rejected(self) -> None:
        long_value = "a" * (_MAX_VARIABLE_VALUE_LENGTH + 1)
        with pytest.raises(ValueError, match="exceeds maximum length"):
            interpolate("desc {{desc}}", {"desc": long_value})

    def test_max_length_accepted(self) -> None:
        value = "a" * _MAX_VARIABLE_VALUE_LENGTH
        result = interpolate("desc {{desc}}", {"desc": value})
        assert result == f"desc {value}"

    def test_safe_value_passes(self) -> None:
        result = interpolate("logging host {{server}}", {"server": "10.0.0.1"})
        assert result == "logging host 10.0.0.1"

    def test_validate_variables_catches_newline(self) -> None:
        pb = Playbook(
            title="Test",
            variables=[PlaybookVariable(name="desc", var_type=VariableType.STRING)],
            steps=["description {{desc}}"],
        )
        errors = validate_variables(pb, {"desc": "port\nshutdown"})
        assert any("control characters" in e for e in errors)

    def test_validate_variables_catches_long_value(self) -> None:
        pb = Playbook(
            title="Test",
            variables=[PlaybookVariable(name="desc", var_type=VariableType.STRING)],
            steps=["description {{desc}}"],
        )
        errors = validate_variables(pb, {"desc": "x" * (_MAX_VARIABLE_VALUE_LENGTH + 1)})
        assert any("exceeds maximum length" in e for e in errors)

    def test_multi_line_injection_attempt(self) -> None:
        """Simulate the exact attack described in the issue."""
        with pytest.raises(ValueError, match="control characters"):
            interpolate(
                "description {{port_description}}",
                {"port_description": "port\nshutdown"},
            )


# ---------------------------------------------------------------------------
# INTERFACE type validation tests (NET-62)
# ---------------------------------------------------------------------------


class TestInterfaceValidation:
    def test_valid_gigabit(self) -> None:
        assert _INTERFACE_PATTERN.match("Gi1/0/1")

    def test_valid_ethernet(self) -> None:
        assert _INTERFACE_PATTERN.match("Ethernet0/1")

    def test_valid_vlan(self) -> None:
        assert _INTERFACE_PATTERN.match("Vlan100")

    def test_valid_port_channel(self) -> None:
        assert _INTERFACE_PATTERN.match("Po1")

    def test_valid_loopback(self) -> None:
        assert _INTERFACE_PATTERN.match("Loopback0")

    def test_valid_ten_gig(self) -> None:
        assert _INTERFACE_PATTERN.match("Te1/0/1")

    def test_invalid_space(self) -> None:
        assert not _INTERFACE_PATTERN.match("Gi 1/0/1")

    def test_invalid_newline(self) -> None:
        assert not _INTERFACE_PATTERN.match("Gi1/0/1\nshutdown")

    def test_invalid_just_numbers(self) -> None:
        assert not _INTERFACE_PATTERN.match("1/0/1")

    def test_invalid_empty(self) -> None:
        assert not _INTERFACE_PATTERN.match("")

    def test_validate_variables_interface_valid(self) -> None:
        pb = Playbook(
            title="Test",
            variables=[PlaybookVariable(name="intf", var_type=VariableType.INTERFACE)],
            steps=["interface {{intf}}"],
        )
        errors = validate_variables(pb, {"intf": "Gi1/0/1"})
        assert len(errors) == 0

    def test_validate_variables_interface_invalid(self) -> None:
        pb = Playbook(
            title="Test",
            variables=[PlaybookVariable(name="intf", var_type=VariableType.INTERFACE)],
            steps=["interface {{intf}}"],
        )
        errors = validate_variables(pb, {"intf": "not an interface"})
        assert any("valid interface name" in e for e in errors)


# ---------------------------------------------------------------------------
# NX-OS driver selection tests (NET-62)
# ---------------------------------------------------------------------------


class TestNXOSDriverSelection:
    """Verify the engine selects the correct Scrapli driver based on platform."""

    async def test_connect_uses_iosxe_by_default(self) -> None:
        """_connect without platform should use AsyncIOSXEDriver."""
        from unittest.mock import AsyncMock, patch

        from backend.playbook_engine import _connect

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver") as mock_iosxe,
            patch("backend.playbook_engine.AsyncNXOSDriver"),
        ):
            mock_conn = AsyncMock()
            mock_iosxe.return_value = mock_conn
            mock_conn.open = AsyncMock()

            await _connect("10.0.0.1", "admin", "pass", None, 30, platform=None)
            mock_iosxe.assert_called_once()

    async def test_connect_uses_iosxe_for_iosxe_platform(self) -> None:
        from unittest.mock import AsyncMock, patch

        from backend.playbook_engine import _connect

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver") as mock_iosxe,
            patch("backend.playbook_engine.AsyncNXOSDriver"),
        ):
            mock_conn = AsyncMock()
            mock_iosxe.return_value = mock_conn
            mock_conn.open = AsyncMock()

            await _connect("10.0.0.1", "admin", "pass", None, 30, platform="iosxe")
            mock_iosxe.assert_called_once()

    async def test_connect_uses_nxos_for_nxos_platform(self) -> None:
        from unittest.mock import AsyncMock, patch

        from backend.playbook_engine import _connect

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver"),
            patch("backend.playbook_engine.AsyncNXOSDriver") as mock_nxos,
        ):
            mock_conn = AsyncMock()
            mock_nxos.return_value = mock_conn
            mock_conn.open = AsyncMock()

            await _connect("10.0.0.1", "admin", "pass", None, 30, platform="nxos")
            mock_nxos.assert_called_once()

    async def test_connect_uses_nxos_case_insensitive(self) -> None:
        from unittest.mock import AsyncMock, patch

        from backend.playbook_engine import _connect

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver"),
            patch("backend.playbook_engine.AsyncNXOSDriver") as mock_nxos,
        ):
            mock_conn = AsyncMock()
            mock_nxos.return_value = mock_conn
            mock_conn.open = AsyncMock()

            await _connect("10.0.0.1", "admin", "pass", None, 30, platform="NXOS")
            mock_nxos.assert_called_once()


# ---------------------------------------------------------------------------
# Execution engine tests (mocked Scrapli)
# ---------------------------------------------------------------------------


class TestPlaybookExecution:
    """Tests for execute_playbook, undo_execution, and _execute_on_device
    with fully mocked Scrapli connections."""

    def _mock_conn(self) -> AsyncMock:
        from unittest.mock import AsyncMock, MagicMock

        conn = AsyncMock()
        conn.open = AsyncMock()
        conn.close = AsyncMock()
        resp = MagicMock()
        resp.result = "mocked output"
        conn.send_command = AsyncMock(return_value=resp)
        conn.send_configs = AsyncMock()
        return conn

    def _base_playbook(self, **overrides: Any) -> Playbook:
        """Create a minimal playbook for testing."""
        defaults: dict[str, Any] = {
            "title": "Test Playbook",
            "steps": ["interface Gi1/0/1", "no shutdown"],
            "pre_checks": ["show interfaces Gi1/0/1 status"],
            "post_checks": ["show interfaces Gi1/0/1 status"],
            "rollback": ["interface Gi1/0/1", "shutdown"],
        }
        defaults.update(overrides)
        return Playbook(**defaults)

    def _base_request(self, **overrides: Any) -> PlaybookExecuteRequest:
        """Create a minimal execute request for testing."""
        defaults: dict[str, Any] = {
            "device_ids": ["switch-1"],
            "device_ips": {"switch-1": "10.0.0.1"},
            "device_platforms": {"switch-1": "iosxe"},
            "variables": {},
            "write_memory": False,
            "username": "admin",
            "password": "secret",
        }
        defaults.update(overrides)
        return PlaybookExecuteRequest(**defaults)

    async def test_execute_single_device_success(self) -> None:
        """Successful execution on a single device: status SUCCESS,
        pre/post outputs captured, commands_sent populated."""
        from unittest.mock import patch

        from backend.playbook_engine import execute_playbook

        conn = self._mock_conn()
        pb = self._base_playbook()
        req = self._base_request()

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver", return_value=conn),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await execute_playbook(pb, req)

        assert result.overall_status == ExecutionStatus.SUCCESS
        assert len(result.device_results) == 1

        dev = result.device_results[0]
        assert dev.device_id == "switch-1"
        assert dev.status == ExecutionStatus.SUCCESS
        assert len(dev.pre_check_outputs) > 0
        assert len(dev.post_check_outputs) > 0
        assert len(dev.commands_sent) > 0

    async def test_execute_stops_on_first_failure(self) -> None:
        """Two devices targeted; first fails (send_configs raises). Only 1 result,
        execution stops early. Since fewer devices were attempted than requested,
        overall status is PARTIAL."""
        from unittest.mock import AsyncMock, patch

        from backend.playbook_engine import execute_playbook

        conn = self._mock_conn()
        conn.send_configs = AsyncMock(side_effect=Exception("config push failed"))

        pb = self._base_playbook()
        req = self._base_request(
            device_ids=["switch-1", "switch-2"],
            device_ips={"switch-1": "10.0.0.1", "switch-2": "10.0.0.2"},
            device_platforms={"switch-1": "iosxe", "switch-2": "iosxe"},
        )

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver", return_value=conn),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await execute_playbook(pb, req)

        # Engine stops on first failure; with 1 of 2 devices attempted -> PARTIAL
        assert result.overall_status == ExecutionStatus.PARTIAL
        assert len(result.device_results) == 1
        assert result.device_results[0].status == ExecutionStatus.FAILED
        assert "config push failed" in (result.device_results[0].error or "")

    async def test_execute_captures_pre_post_checks(self) -> None:
        """Verify pre_check_outputs and post_check_outputs dicts are populated
        with the correct command keys and mocked output values."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from backend.playbook_engine import execute_playbook

        conn = self._mock_conn()
        pre_resp = MagicMock()
        pre_resp.result = "pre-check output"
        post_resp = MagicMock()
        post_resp.result = "post-check output"

        call_count = 0

        async def _send_cmd(cmd: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            # Pre-checks are called first, post-checks after send_configs
            if call_count <= 1:
                return pre_resp
            return post_resp

        conn.send_command = AsyncMock(side_effect=_send_cmd)

        pb = self._base_playbook(
            pre_checks=["show version"],
            post_checks=["show ip interface brief"],
        )
        req = self._base_request()

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver", return_value=conn),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await execute_playbook(pb, req)

        dev = result.device_results[0]
        assert dev.pre_check_outputs.get("show version") == "pre-check output"
        assert dev.post_check_outputs.get("show ip interface brief") == "post-check output"

    async def test_execute_write_memory_iosxe(self) -> None:
        """write_memory=True on IOS-XE should send 'write memory'."""
        from unittest.mock import patch

        from backend.playbook_engine import execute_playbook

        conn = self._mock_conn()
        pb = self._base_playbook()
        req = self._base_request(write_memory=True)

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver", return_value=conn),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await execute_playbook(pb, req)

        dev = result.device_results[0]
        assert dev.status == ExecutionStatus.SUCCESS
        assert "write memory" in dev.commands_sent

        # Verify send_command was called with "write memory"
        write_calls = [c for c in conn.send_command.call_args_list if c.args[0] == "write memory"]
        assert len(write_calls) == 1

    async def test_execute_write_memory_nxos(self) -> None:
        """write_memory=True on NX-OS should send 'copy running-config startup-config'."""
        from unittest.mock import patch

        from backend.playbook_engine import execute_playbook

        conn = self._mock_conn()
        pb = self._base_playbook()
        req = self._base_request(
            device_platforms={"switch-1": "nxos"},
            write_memory=True,
        )

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver"),
            patch("backend.playbook_engine.AsyncNXOSDriver", return_value=conn),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await execute_playbook(pb, req)

        dev = result.device_results[0]
        assert dev.status == ExecutionStatus.SUCCESS
        assert "copy running-config startup-config" in dev.commands_sent

        save_calls = [
            c
            for c in conn.send_command.call_args_list
            if c.args[0] == "copy running-config startup-config"
        ]
        assert len(save_calls) == 1

    async def test_execute_variable_validation_failure(self) -> None:
        """Required variable missing should produce FAILED with error message."""
        from backend.playbook_engine import execute_playbook

        pb = self._base_playbook(
            variables=[
                PlaybookVariable(name="vlan_id", var_type=VariableType.INT, required=True),
            ],
            steps=["vlan {{vlan_id}}"],
        )
        req = self._base_request(variables={})

        result = await execute_playbook(pb, req)

        assert result.overall_status == ExecutionStatus.FAILED
        assert result.error is not None
        assert "vlan_id" in result.error

    async def test_execute_safety_check_failure(self) -> None:
        """Playbook containing 'erase' command should be blocked."""
        from backend.playbook_engine import execute_playbook

        pb = self._base_playbook(steps=["erase startup-config"])
        req = self._base_request()

        result = await execute_playbook(pb, req)

        assert result.overall_status == ExecutionStatus.FAILED
        assert result.error is not None
        assert "safety" in result.error.lower() or "blocked" in result.error.lower()

    async def test_execute_max_targets_exceeded(self) -> None:
        """More device_ids than playbook_max_targets (default 10) should fail."""
        from backend.playbook_engine import execute_playbook

        device_ids = [f"switch-{i}" for i in range(11)]
        device_ips = {did: f"10.0.0.{i}" for i, did in enumerate(device_ids, start=1)}

        pb = self._base_playbook()
        req = self._base_request(device_ids=device_ids, device_ips=device_ips)

        result = await execute_playbook(pb, req)

        assert result.overall_status == ExecutionStatus.FAILED
        assert result.error is not None
        assert "too many" in result.error.lower() or "max" in result.error.lower()

    async def test_execute_missing_device_ip(self) -> None:
        """device_id without matching IP in device_ips should fail."""
        from unittest.mock import patch

        from backend.playbook_engine import execute_playbook

        pb = self._base_playbook()
        req = self._base_request(
            device_ids=["switch-1"],
            device_ips={},  # no IP mapping
        )

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver"),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await execute_playbook(pb, req)

        assert result.overall_status == ExecutionStatus.FAILED
        assert len(result.device_results) == 1
        assert result.device_results[0].status == ExecutionStatus.FAILED
        assert "no ip" in (result.device_results[0].error or "").lower()

    async def test_undo_execution_success(self) -> None:
        """Undo with rollback commands should send them via send_configs."""
        from unittest.mock import patch

        from backend.playbook_engine import undo_execution

        conn = self._mock_conn()

        execution = PlaybookExecution(
            id="exec-1",
            playbook_id="pb-1",
            playbook_title="Test Playbook",
            timestamp=datetime.now(UTC),
            overall_status=ExecutionStatus.SUCCESS,
            device_results=[
                DeviceExecutionResult(
                    device_id="switch-1",
                    device_ip="10.0.0.1",
                    status=ExecutionStatus.SUCCESS,
                    rollback_commands=["interface Gi1/0/1", "shutdown"],
                ),
            ],
        )

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver", return_value=conn),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await undo_execution(execution, "admin", "secret")

        assert result.overall_status == ExecutionStatus.SUCCESS
        assert len(result.device_results) == 1
        assert result.device_results[0].status == ExecutionStatus.SUCCESS

        conn.send_configs.assert_called_once_with(["interface Gi1/0/1", "shutdown"])

    async def test_undo_execution_no_rollback_commands(self) -> None:
        """Device result without rollback_commands should produce FAILED per device."""
        from backend.playbook_engine import undo_execution

        execution = PlaybookExecution(
            id="exec-2",
            playbook_id="pb-1",
            playbook_title="Test Playbook",
            timestamp=datetime.now(UTC),
            overall_status=ExecutionStatus.SUCCESS,
            device_results=[
                DeviceExecutionResult(
                    device_id="switch-1",
                    device_ip="10.0.0.1",
                    status=ExecutionStatus.SUCCESS,
                    rollback_commands=[],  # no rollback
                ),
            ],
        )

        result = await undo_execution(execution, "admin", "secret")

        assert len(result.device_results) == 1
        assert result.device_results[0].status == ExecutionStatus.FAILED
        assert "no rollback" in (result.device_results[0].error or "").lower()

    async def test_execute_partial_status(self) -> None:
        """3 devices: first succeeds, second fails (stops). Overall should be PARTIAL
        since only 2 of 3 devices were attempted."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from backend.playbook_engine import execute_playbook

        call_count = 0

        def _make_conn() -> AsyncMock:
            """Each driver instantiation creates a fresh connection mock."""
            nonlocal call_count
            call_count += 1
            c = AsyncMock()
            c.open = AsyncMock()
            c.close = AsyncMock()
            resp = MagicMock()
            resp.result = "ok"
            c.send_command = AsyncMock(return_value=resp)
            if call_count == 1:
                c.send_configs = AsyncMock()  # first device succeeds
            else:
                c.send_configs = AsyncMock(
                    side_effect=Exception("connection lost")
                )  # second device fails
            return c

        pb = self._base_playbook()
        req = self._base_request(
            device_ids=["switch-1", "switch-2", "switch-3"],
            device_ips={
                "switch-1": "10.0.0.1",
                "switch-2": "10.0.0.2",
                "switch-3": "10.0.0.3",
            },
            device_platforms={
                "switch-1": "iosxe",
                "switch-2": "iosxe",
                "switch-3": "iosxe",
            },
        )

        with (
            patch(
                "backend.playbook_engine.AsyncIOSXEDriver",
                side_effect=_make_conn,
            ),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await execute_playbook(pb, req)

        assert result.overall_status == ExecutionStatus.PARTIAL
        assert len(result.device_results) == 2
        assert result.device_results[0].status == ExecutionStatus.SUCCESS
        assert result.device_results[1].status == ExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# Configure replace tests
# ---------------------------------------------------------------------------


class TestConfigureReplace:
    """Tests for configure replace mode (IOS-XE 16.x+)."""

    def _mock_conn(self) -> AsyncMock:
        conn = AsyncMock()
        conn.open = AsyncMock()
        conn.close = AsyncMock()
        resp = MagicMock()
        resp.result = "mocked output"
        conn.send_command = AsyncMock(return_value=resp)
        conn.send_configs = AsyncMock()
        return conn

    async def test_replace_mode_backs_up_config(self) -> None:
        """configure replace mode should back up running-config before applying."""
        from unittest.mock import patch

        from backend.playbook_engine import execute_playbook

        conn = self._mock_conn()
        pb = Playbook(
            title="Replace Test",
            steps=["interface Gi1/0/1", "no shutdown"],
            config_mode=ConfigMode.REPLACE,
        )
        req = PlaybookExecuteRequest(
            device_ids=["sw1"],
            device_ips={"sw1": "10.0.0.1"},
            device_platforms={"sw1": "iosxe"},
            variables={},
            write_memory=False,
            username="admin",
            password="secret",
        )

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver", return_value=conn),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await execute_playbook(pb, req)

        assert result.overall_status == ExecutionStatus.SUCCESS
        # Verify backup command was sent
        backup_calls = [
            c
            for c in conn.send_command.call_args_list
            if "copy running-config flash:netscope-pre-replace.cfg" in str(c)
        ]
        assert len(backup_calls) >= 1

    async def test_replace_mode_rejects_nxos(self) -> None:
        """configure replace on NX-OS device should fail early."""
        from backend.playbook_engine import execute_playbook

        pb = Playbook(
            title="Replace Test",
            steps=["feature nxapi"],
            config_mode=ConfigMode.REPLACE,
        )
        req = PlaybookExecuteRequest(
            device_ids=["sw1"],
            device_ips={"sw1": "10.0.0.1"},
            device_platforms={"sw1": "nxos"},
            variables={},
            write_memory=False,
            username="admin",
            password="secret",
        )

        result = await execute_playbook(pb, req)

        assert result.overall_status == ExecutionStatus.FAILED
        assert "configure replace" in (result.error or "").lower()
        assert "IOS-XE" in (result.error or "")

    async def test_merge_mode_is_default(self) -> None:
        """Default config_mode should be merge."""
        pb = Playbook(title="Default", steps=["show version"])
        assert pb.config_mode == ConfigMode.MERGE

    async def test_configure_replace_standalone_function(self) -> None:
        """Test the standalone configure_replace function."""
        from unittest.mock import patch

        from backend.playbook_engine import configure_replace

        conn = self._mock_conn()

        with (
            patch("backend.playbook_engine.AsyncIOSXEDriver", return_value=conn),
            patch("backend.playbook_engine.AsyncNXOSDriver"),
            patch("backend.discovery._base_opts", return_value={}),
        ):
            result = await configure_replace(
                device_ip="10.0.0.1",
                config_url="flash:backup-config",
                username="admin",
                password="secret",
            )

        assert result["status"] == "success"

    async def test_configure_replace_rejects_nxos_standalone(self) -> None:
        """Standalone configure_replace should reject NX-OS."""
        from backend.playbook_engine import configure_replace

        result = await configure_replace(
            device_ip="10.0.0.1",
            config_url="flash:backup-config",
            platform="nxos",
            username="admin",
            password="secret",
        )

        assert result["status"] == "failed"
        assert "IOS-XE" in (result.get("error") or "")
