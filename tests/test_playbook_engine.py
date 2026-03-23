"""Tests for playbook execution engine."""

from __future__ import annotations

from typing import Any

import pytest

from backend.playbook_engine import dry_run, execute_playbook, undo_execution
from backend.playbooks import (
    ConfigMode,
    ExecutionStatus,
    Playbook,
    PlaybookExecuteRequest,
    PlaybookVariable,
)
from tests.conftest import MockAsyncIOSXEDriver
from tests.fixtures.cli_outputs import VALID_PASSWORD, VALID_USERNAME


def _make_playbook(**overrides: Any) -> Playbook:
    defaults: dict[str, Any] = {
        "title": "Test Playbook",
        "description": "A test playbook",
        "pre_checks": ["show vlan brief"],
        "steps": ["interface {{interface}}", "switchport access vlan {{vlan_id}}"],
        "post_checks": ["show vlan brief"],
        "rollback": ["interface {{interface}}", "no switchport access vlan {{vlan_id}}"],
        "variables": [
            PlaybookVariable(name="interface", required=True),
            PlaybookVariable(name="vlan_id", required=True),
        ],
    }
    defaults.update(overrides)
    return Playbook(**defaults)


def _make_request(**overrides: Any) -> PlaybookExecuteRequest:
    defaults: dict[str, Any] = {
        "device_ids": ["SW1"],
        "device_ips": {"SW1": "10.0.0.1"},
        "device_platforms": {"SW1": "iosxe"},
        "variables": {"interface": "GigabitEthernet1/0/1", "vlan_id": "100"},
        "username": VALID_USERNAME,
        "password": VALID_PASSWORD,
    }
    defaults.update(overrides)
    return PlaybookExecuteRequest(**defaults)


def _mock_connect(**kwargs: Any) -> MockAsyncIOSXEDriver:
    """Create a MockAsyncIOSXEDriver that's pre-opened."""
    mock = MockAsyncIOSXEDriver(host=kwargs.get("host", "10.0.0.1"))
    mock._is_open = True
    mock._device_outputs = {
        "show vlan brief": "VLAN Name\n---- ----\n1    default\n100  USERS",
    }
    return mock


@pytest.fixture(autouse=True)
def patch_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace _connect with a mock that returns a pre-opened driver."""

    async def fake_connect(*args: Any, **kwargs: Any) -> MockAsyncIOSXEDriver:
        return _mock_connect(**kwargs)

    monkeypatch.setattr("backend.playbook_engine._connect", fake_connect)


# ---------------------------------------------------------------------------
# execute_playbook tests
# ---------------------------------------------------------------------------


async def test_execute_success() -> None:
    pb = _make_playbook()
    req = _make_request()
    result = await execute_playbook(pb, req)
    assert result.overall_status == ExecutionStatus.SUCCESS
    assert len(result.device_results) == 1
    assert result.device_results[0].device_id == "SW1"
    assert result.device_results[0].status == ExecutionStatus.SUCCESS
    assert len(result.device_results[0].commands_sent) > 0


async def test_execute_multi_device() -> None:
    pb = _make_playbook()
    req = _make_request(
        device_ids=["SW1", "SW2"],
        device_ips={"SW1": "10.0.0.1", "SW2": "10.0.0.2"},
    )
    result = await execute_playbook(pb, req)
    assert result.overall_status == ExecutionStatus.SUCCESS
    assert len(result.device_results) == 2


async def test_execute_stops_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    async def failing_connect(*args: Any, **kwargs: Any) -> MockAsyncIOSXEDriver:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionRefusedError("Connection refused")
        return _mock_connect(**kwargs)

    monkeypatch.setattr("backend.playbook_engine._connect", failing_connect)

    pb = _make_playbook()
    req = _make_request(
        device_ids=["SW1", "SW2"],
        device_ips={"SW1": "10.0.0.1", "SW2": "10.0.0.2"},
    )
    result = await execute_playbook(pb, req)
    assert result.device_results[0].status == ExecutionStatus.FAILED
    assert len(result.device_results) == 1  # Stopped after first failure


async def test_execute_too_many_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.playbook_engine.settings.playbook_max_targets", 1)
    pb = _make_playbook()
    req = _make_request(
        device_ids=["SW1", "SW2"],
        device_ips={"SW1": "10.0.0.1", "SW2": "10.0.0.2"},
    )
    result = await execute_playbook(pb, req)
    assert result.overall_status == ExecutionStatus.FAILED
    assert "Too many targets" in (result.error or "")


async def test_execute_variable_validation_fails() -> None:
    pb = _make_playbook()
    req = _make_request(variables={})  # Missing required variables
    result = await execute_playbook(pb, req)
    assert result.overall_status == ExecutionStatus.FAILED
    assert "Variable validation failed" in (result.error or "")


async def test_execute_safety_check_fails() -> None:
    pb = _make_playbook(
        pre_checks=[],
        steps=["reload"],
        post_checks=[],
        rollback=[],
        variables=[],
    )
    req = _make_request(variables={})
    result = await execute_playbook(pb, req)
    assert result.overall_status == ExecutionStatus.FAILED
    assert "Safety check failed" in (result.error or "")


async def test_execute_write_memory() -> None:
    pb = _make_playbook()
    req = _make_request(write_memory=True)
    result = await execute_playbook(pb, req)
    assert result.overall_status == ExecutionStatus.SUCCESS
    assert "write memory" in result.device_results[0].commands_sent


async def test_execute_nxos_write_memory() -> None:
    pb = _make_playbook()
    req = _make_request(
        write_memory=True,
        device_platforms={"SW1": "nxos"},
    )
    result = await execute_playbook(pb, req)
    assert result.overall_status == ExecutionStatus.SUCCESS
    assert "copy running-config startup-config" in result.device_results[0].commands_sent


async def test_execute_configure_replace_nxos_rejected() -> None:
    pb = _make_playbook(config_mode=ConfigMode.REPLACE)
    req = _make_request(device_platforms={"SW1": "nxos"})
    result = await execute_playbook(pb, req)
    assert result.overall_status == ExecutionStatus.FAILED
    assert "IOS-XE" in (result.error or "")


async def test_execute_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_connect(*args: Any, **kwargs: Any) -> None:
        raise TimeoutError("SSH timeout")

    monkeypatch.setattr("backend.playbook_engine._connect", broken_connect)
    pb = _make_playbook()
    req = _make_request()
    result = await execute_playbook(pb, req)
    assert result.device_results[0].status == ExecutionStatus.FAILED
    assert "SSH timeout" in (result.device_results[0].error or "")


# ---------------------------------------------------------------------------
# dry_run tests
# ---------------------------------------------------------------------------


async def test_dry_run_basic() -> None:
    pb = _make_playbook()
    result = await dry_run(pb, {"interface": "Gi1/0/1", "vlan_id": "100"})
    assert result["errors"] == []
    assert "interface Gi1/0/1" in result["steps"]
    assert "switchport access vlan 100" in result["steps"]


async def test_dry_run_with_missing_variable() -> None:
    pb = _make_playbook()
    result = await dry_run(pb, {})  # Missing required vars
    assert len(result["errors"]) > 0


# ---------------------------------------------------------------------------
# undo tests
# ---------------------------------------------------------------------------


async def test_undo_execution() -> None:
    pb = _make_playbook()
    req = _make_request()
    execution = await execute_playbook(pb, req)
    assert execution.overall_status == ExecutionStatus.SUCCESS

    undo_result = await undo_execution(execution, username=VALID_USERNAME, password=VALID_PASSWORD)
    assert undo_result.overall_status == ExecutionStatus.SUCCESS


async def test_undo_no_rollback_commands() -> None:
    pb = _make_playbook(rollback=[])
    req = _make_request()
    execution = await execute_playbook(pb, req)

    undo_result = await undo_execution(execution, username=VALID_USERNAME, password=VALID_PASSWORD)
    assert any(
        r.status == ExecutionStatus.FAILED and "No rollback" in (r.error or "")
        for r in undo_result.device_results
    )
