"""Tests for settings persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.settings_store import SettingsStore, SQLiteSettingsStore, make_settings_store

# ---------------------------------------------------------------------------
# In-memory SettingsStore tests
# ---------------------------------------------------------------------------


class TestSettingsStore:
    def test_get_returns_defaults(self) -> None:
        store = SettingsStore()
        data = store.get()
        assert "discovery" in data
        assert "general" in data
        assert data["general"]["max_sessions"] > 0

    def test_update_discovery_settings(self) -> None:
        store = SettingsStore()
        result = store.update({"discovery": {"timeout": 60, "max_hops": 5}})
        assert result["discovery"]["timeout"] == 60
        assert result["discovery"]["max_hops"] == 5
        # Other defaults preserved
        assert result["discovery"]["max_concurrency"] == 10

    def test_update_credential_profiles(self) -> None:
        store = SettingsStore()
        profiles = [{"name": "lab", "username": "admin", "_internal": "strip"}]
        result = store.update({"credential_profiles": profiles})
        assert len(result["credential_profiles"]) == 1
        assert result["credential_profiles"][0]["name"] == "lab"
        # Internal fields stripped
        assert "_internal" not in result["credential_profiles"][0]

    def test_update_collection_profile(self) -> None:
        store = SettingsStore()
        result = store.update({"collection_profile": "minimal"})
        assert result["collection_profile"] == "minimal"

    def test_update_custom_groups(self) -> None:
        store = SettingsStore()
        groups = [{"name": "floor1", "devices": ["SW1", "SW2"]}]
        result = store.update({"custom_groups": groups})
        assert result["custom_groups"] == groups

    def test_update_general_settings(self) -> None:
        store = SettingsStore()
        store.update({"general": {"log_level": "debug", "max_sessions": 100}})
        # log_level is always overridden by the env-backed Settings() in get(),
        # so verify the stored internal value directly
        assert store._data["general"]["log_level"] == "debug"
        assert store._data["general"]["max_sessions"] == 100

    def test_reset_restores_defaults(self) -> None:
        store = SettingsStore()
        store.update({"discovery": {"timeout": 999}})
        result = store.reset()
        assert result["discovery"]["timeout"] == 30

    def test_overrides_field_present(self) -> None:
        store = SettingsStore()
        data = store.get()
        assert "overrides" in data
        assert isinstance(data["overrides"], dict)


# ---------------------------------------------------------------------------
# SQLiteSettingsStore tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "settings.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    return conn


class TestSQLiteSettingsStore:
    def test_get_returns_defaults_on_fresh_db(self, sqlite_conn: sqlite3.Connection) -> None:
        store = SQLiteSettingsStore(sqlite_conn)
        data = store.get()
        assert "discovery" in data
        assert data["discovery"]["timeout"] == 30

    def test_update_persists_to_db(self, sqlite_conn: sqlite3.Connection) -> None:
        store = SQLiteSettingsStore(sqlite_conn)
        store.update({"discovery": {"timeout": 120}})

        # Read raw from DB
        row = sqlite_conn.execute(
            "SELECT value FROM settings WHERE key = 'app_settings'"
        ).fetchone()
        assert row is not None
        import json

        saved = json.loads(row[0])
        assert saved["discovery"]["timeout"] == 120

    def test_reload_from_db(self, sqlite_conn: sqlite3.Connection) -> None:
        """A new store instance should load previously saved settings."""
        store1 = SQLiteSettingsStore(sqlite_conn)
        store1.update({"discovery": {"timeout": 99}})

        store2 = SQLiteSettingsStore(sqlite_conn)
        data = store2.get()
        assert data["discovery"]["timeout"] == 99

    def test_reset_persists(self, sqlite_conn: sqlite3.Connection) -> None:
        store = SQLiteSettingsStore(sqlite_conn)
        store.update({"discovery": {"timeout": 999}})
        store.reset()

        store2 = SQLiteSettingsStore(sqlite_conn)
        data = store2.get()
        assert data["discovery"]["timeout"] == 30


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestMakeSettingsStore:
    def test_returns_memory_store_without_conn(self) -> None:
        store = make_settings_store()
        assert isinstance(store, SettingsStore)
        assert not isinstance(store, SQLiteSettingsStore)

    def test_returns_sqlite_store_with_conn(self, sqlite_conn: sqlite3.Connection) -> None:
        store = make_settings_store(sqlite_conn)
        assert isinstance(store, SQLiteSettingsStore)
