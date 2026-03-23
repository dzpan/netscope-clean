"""Tests for device config dump collection."""

from __future__ import annotations

from typing import Any

import pytest

from backend.config_dump import DUMP_COMMANDS, _build_cred_list, run_config_dump
from backend.models import ConfigDumpRequest, CredentialSet
from tests.conftest import MockCommandResponse


class MockDumpDriver:
    """Simplified mock for config dump (doesn't need DEVICE_REGISTRY)."""

    def __init__(self, *, fail_auth: bool = False, fail_commands: list[str] | None = None):
        self._fail_auth = fail_auth
        self._fail_commands = fail_commands or []
        self._is_open = False

    async def open(self) -> None:
        if self._fail_auth:
            raise Exception("SSH authentication failed")
        self._is_open = True

    async def send_command(self, command: str) -> MockCommandResponse:
        if command in self._fail_commands:
            raise Exception(f"Command failed: {command}")
        if command == "show version":
            return MockCommandResponse(result="Cisco IOS XE 17.3.1")
        if command == "show running-config":
            return MockCommandResponse(result="! Running config\nhostname SW1")
        if command == "show ip interface brief":
            return MockCommandResponse(result="% Invalid input detected")
        return MockCommandResponse(result=f"output of {command}")

    async def close(self) -> None:
        self._is_open = False


def _make_request(**overrides: Any) -> ConfigDumpRequest:
    defaults: dict[str, Any] = {
        "device_ip": "10.0.0.1",
        "device_id": "SW1",
        "username": "admin",
        "password": "cisco",
    }
    defaults.update(overrides)
    return ConfigDumpRequest(**defaults)


@pytest.fixture(autouse=True)
def patch_scrapli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch out scrapli imports in config_dump."""
    import backend.config_dump as cd_mod
    import backend.discovery as disc_mod

    monkeypatch.setattr(cd_mod, "SCRAPLI_AVAILABLE", True)
    monkeypatch.setattr(disc_mod, "SCRAPLI_AVAILABLE", True)


# ---------------------------------------------------------------------------
# run_config_dump tests
# ---------------------------------------------------------------------------


async def test_dump_success(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = MockDumpDriver()
    monkeypatch.setattr(
        "backend.config_dump.AsyncIOSXEDriver",
        lambda **kw: driver,
    )
    req = _make_request()
    dump = await run_config_dump(req)
    assert dump.device_id == "SW1"
    assert dump.device_ip == "10.0.0.1"
    assert len(dump.commands) == len(DUMP_COMMANDS)
    version_cmd = next(c for c in dump.commands if c.command == "show version")
    assert "Cisco IOS XE" in version_cmd.output


async def test_dump_command_error_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Commands returning '% Invalid input' should be captured as errors."""
    driver = MockDumpDriver()
    monkeypatch.setattr(
        "backend.config_dump.AsyncIOSXEDriver",
        lambda **kw: driver,
    )
    req = _make_request()
    dump = await run_config_dump(req)
    ip_brief = next(c for c in dump.commands if c.command == "show ip interface brief")
    assert ip_brief.error is not None
    assert "Invalid input" in ip_brief.error


async def test_dump_command_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """A command that raises should be captured, not abort the dump."""
    driver = MockDumpDriver(fail_commands=["show cdp neighbors detail"])
    monkeypatch.setattr(
        "backend.config_dump.AsyncIOSXEDriver",
        lambda **kw: driver,
    )
    req = _make_request()
    dump = await run_config_dump(req)
    cdp_cmd = next(c for c in dump.commands if c.command == "show cdp neighbors detail")
    assert cdp_cmd.error is not None
    assert any(c.output for c in dump.commands)


async def test_dump_auth_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """First creds fail, second succeed."""
    call_count = 0

    def make_driver(**kw: Any) -> MockDumpDriver:
        nonlocal call_count
        call_count += 1
        return MockDumpDriver(fail_auth=(call_count == 1))

    monkeypatch.setattr("backend.config_dump.AsyncIOSXEDriver", make_driver)
    req = _make_request(
        credential_sets=[
            CredentialSet(username="bad", password="bad"),
            CredentialSet(username="admin", password="cisco"),
        ]
    )
    dump = await run_config_dump(req)
    assert dump.device_id == "SW1"
    assert call_count == 2


async def test_dump_all_auth_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.config_dump.AsyncIOSXEDriver",
        lambda **kw: MockDumpDriver(fail_auth=True),
    )
    req = _make_request()
    with pytest.raises(Exception):
        await run_config_dump(req)


async def test_dump_no_credentials() -> None:
    req = ConfigDumpRequest(device_ip="10.0.0.1", username="", password="")
    with pytest.raises(RuntimeError, match="No credentials"):
        await run_config_dump(req)


# ---------------------------------------------------------------------------
# _build_cred_list tests
# ---------------------------------------------------------------------------


def test_build_cred_list_dedup() -> None:
    """Primary cred already in credential_sets should not be duplicated."""
    req = _make_request(
        username="admin",
        password="cisco",
        credential_sets=[CredentialSet(username="admin", password="cisco")],
    )
    creds = _build_cred_list(req)
    assert len(creds) == 1


def test_build_cred_list_appends_primary() -> None:
    req = _make_request(
        username="admin",
        password="cisco",
        credential_sets=[CredentialSet(username="other", password="pass")],
    )
    creds = _build_cred_list(req)
    assert len(creds) == 2
