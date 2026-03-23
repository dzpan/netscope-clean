"""Shared test fixtures and mock SSH infrastructure for E2E testing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.fixtures.cli_outputs import DEVICE_REGISTRY, VALID_PASSWORD, VALID_USERNAME

# ---------------------------------------------------------------------------
# Mock Scrapli driver — simulates AsyncIOSXEDriver without real SSH
# ---------------------------------------------------------------------------


@dataclass
class MockCommandResponse:
    """Mimics scrapli Response with a .result attribute."""

    result: str


@dataclass
class MockAsyncIOSXEDriver:
    """Drop-in replacement for scrapli AsyncIOSXEDriver using canned CLI outputs.

    Auth is simulated: if the username/password don't match the fixture
    credentials, ``open()`` raises an auth-like exception — exactly as
    scrapli would with real SSH.
    """

    host: str
    auth_username: str = ""
    auth_password: str = ""
    auth_secondary: str | None = None
    auth_strict_key: bool = False
    transport: str = "asyncssh"
    timeout_socket: int = 30
    timeout_transport: int = 30
    timeout_ops: int = 30
    on_open: Any = None

    # Internal state
    _is_open: bool = field(default=False, init=False, repr=False)
    _device_outputs: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    default_desired_privilege_level: str = field(default="privilege_exec", init=False)

    # Simulated network delay (seconds) — can be tuned per-test
    latency: float = field(default=0.0, init=False, repr=False)

    # Track configs sent for test assertions
    _sent_configs: list[str] = field(default_factory=list, init=False, repr=False)
    # If set, send_configs raises this exception
    _send_configs_error: Exception | None = field(default=None, init=False, repr=False)

    async def open(self) -> None:
        """Simulate SSH open with credential validation."""
        await asyncio.sleep(self.latency)

        if self.host not in DEVICE_REGISTRY:
            raise ConnectionRefusedError(f"Connection refused to {self.host}")

        if self.auth_username != VALID_USERNAME or self.auth_password != VALID_PASSWORD:
            raise Exception(f"SSH authentication failed for {self.auth_username}@{self.host}")

        self._device_outputs = DEVICE_REGISTRY[self.host]
        self._is_open = True

        # Call on_open handler if provided (terminal setup)
        if self.on_open is not None:
            await self.on_open(self)

    async def send_command(self, command: str) -> MockCommandResponse:
        """Return canned output for a known command."""
        if not self._is_open:
            raise Exception("Connection not opened — call open() first")
        await asyncio.sleep(self.latency)
        output = self._device_outputs.get(command, "")
        return MockCommandResponse(result=output)

    async def send_configs(
        self,
        configs: list[str],
        *,
        timeout_ops: int | None = None,
    ) -> list[MockCommandResponse]:
        """Simulate sending config commands. Stores them for assertion."""
        if not self._is_open:
            raise Exception("Connection not opened — call open() first")
        if self._send_configs_error is not None:
            raise self._send_configs_error
        await asyncio.sleep(self.latency)
        self._sent_configs.extend(configs)
        return [MockCommandResponse(result="") for _ in configs]

    async def get_prompt(self) -> str:
        hostname = self._device_outputs.get("_hostname", self.host)
        return f"{hostname}#"

    async def acquire_priv(self, desired_priv: str = "privilege_exec") -> None:
        pass

    async def close(self) -> None:
        self._is_open = False


def _mock_driver_factory(**kwargs: Any) -> MockAsyncIOSXEDriver:
    """Factory that matches AsyncIOSXEDriver(**opts) call signature."""
    return MockAsyncIOSXEDriver(**kwargs)


@pytest.fixture()
def mock_scrapli(monkeypatch: pytest.MonkeyPatch) -> type[MockAsyncIOSXEDriver]:
    """Monkey-patch the discovery module to use MockAsyncIOSXEDriver.

    Returns the mock class so tests can inspect or customize it.
    """
    import backend.discovery as disc_mod

    monkeypatch.setattr(disc_mod, "AsyncIOSXEDriver", _mock_driver_factory)
    monkeypatch.setattr(disc_mod, "SCRAPLI_AVAILABLE", True)
    return MockAsyncIOSXEDriver


@pytest.fixture(autouse=True)
def _disable_rate_limit() -> None:
    """Disable rate limiting in tests to prevent cross-test 429 flakiness."""
    from backend.rate_limit import limiter

    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture()
def clean_store() -> None:
    """Ensure the in-memory session store is empty before each test."""
    from backend.store import store

    if hasattr(store, "_sessions"):
        store._sessions.clear()  # type: ignore[attr-defined]


@pytest.fixture()
async def async_client():
    """Async httpx client wired to the FastAPI app."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
