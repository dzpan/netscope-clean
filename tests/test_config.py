"""Tests for application settings validation."""

from __future__ import annotations

import logging
import os

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent NETSCOPE_* env vars from polluting settings tests."""
    for key in list(os.environ):
        if key.startswith("NETSCOPE_"):
            monkeypatch.delenv(key, raising=False)


def test_auth_enabled_requires_secret_key() -> None:
    """Settings must raise if auth_enabled=True but secret_key is empty."""
    from pydantic import ValidationError

    from backend.config import Settings

    with pytest.raises(ValidationError, match="NETSCOPE_SECRET_KEY"):
        Settings(auth_enabled=True, secret_key="")


def test_auth_enabled_with_secret_key_ok() -> None:
    """Settings should accept auth_enabled=True when secret_key is set."""
    from backend.config import Settings

    s = Settings(auth_enabled=True, secret_key="my-secure-key-1234")
    assert s.auth_enabled is True
    assert s.secret_key == "my-secure-key-1234"


def test_db_path_without_secret_key_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Settings with db_path but no secret_key should log a warning."""
    from backend.config import Settings

    with caplog.at_level(logging.WARNING):
        s = Settings(db_path="/tmp/test.db", secret_key="")
    assert s.db_path == "/tmp/test.db"
    assert "NETSCOPE_SECRET_KEY" in caplog.text


def test_no_auth_no_db_no_warning() -> None:
    """Default settings (no auth, no db) should not raise or warn."""
    from backend.config import Settings

    s = Settings()
    assert s.auth_enabled is False
    assert s.secret_key == ""


def test_allow_advanced_without_password_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Settings with allow_advanced=True but no password should log a warning."""
    from backend.config import Settings

    with caplog.at_level(logging.WARNING):
        s = Settings(allow_advanced=True, advanced_password="")
    assert s.allow_advanced is True
    assert "NETSCOPE_ADVANCED_PASSWORD" in caplog.text
