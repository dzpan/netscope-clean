"""Settings persistence — stores user-configured settings in SQLite or memory.

Settings are layered: defaults → user-saved → env var overrides.
Environment variables (NETSCOPE_*) always win.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from backend.config import Settings

# Fields that can be set from the UI
_UI_FIELDS = {
    "log_level",
    "max_sessions",
    "snapshot_retention_days",
    "rediscovery_interval",
}

# Env-var mapping: field name → env var name
_ENV_MAP = {f: f"NETSCOPE_{f.upper()}" for f in _UI_FIELDS}


def _defaults() -> dict[str, Any]:
    """Return the full default settings payload."""
    return {
        "discovery": {
            "timeout": 30,
            "max_concurrency": 10,
            "max_hops": 2,
            "discovery_protocol": "cdp_prefer",
            "scope": "",
            "auto_follow": False,
        },
        "credential_profiles": [],
        "collection_profile": "standard",
        "custom_groups": [],
        "general": {
            "log_level": "info",
            "max_sessions": 50,
            "snapshot_retention_days": 90,
            "rediscovery_interval": 0,
            "db_path": None,
        },
    }


def _env_overrides() -> dict[str, bool]:
    """Return dict of field names that are set via env vars."""
    overrides: dict[str, bool] = {}
    for field, env_var in _ENV_MAP.items():
        if os.environ.get(env_var):
            overrides[field] = True
    return overrides


class SettingsStore:
    """In-memory settings store (no persistence)."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = _defaults()

    def get(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(json.dumps(self._data))
        # Merge in current env-derived values for general settings
        cfg = Settings()
        result["general"]["log_level"] = cfg.log_level
        result["general"]["max_sessions"] = cfg.max_sessions
        result["general"]["snapshot_retention_days"] = cfg.snapshot_retention_days
        result["general"]["rediscovery_interval"] = cfg.rediscovery_interval
        result["general"]["db_path"] = cfg.db_path
        result["overrides"] = _env_overrides()
        return result

    def update(self, data: dict[str, Any]) -> dict[str, Any]:
        if "discovery" in data:
            self._data["discovery"].update(data["discovery"])
        if "credential_profiles" in data:
            # Strip internal fields
            self._data["credential_profiles"] = [
                {k: v for k, v in c.items() if not k.startswith("_")}
                for c in data["credential_profiles"]
            ]
        if "collection_profile" in data:
            self._data["collection_profile"] = data["collection_profile"]
        if "custom_groups" in data:
            self._data["custom_groups"] = data["custom_groups"]
        if "general" in data:
            for key in _UI_FIELDS:
                if key in data["general"]:
                    self._data["general"][key] = data["general"][key]
        return self.get()

    def reset(self) -> dict[str, Any]:
        self._data = _defaults()
        return self.get()


class SQLiteSettingsStore(SettingsStore):
    """SQLite-backed settings store."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        super().__init__()
        self._conn = conn
        self._load()

    def _load(self) -> None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = 'app_settings'").fetchone()
        if row:
            saved = json.loads(row[0])
            # Merge saved data into defaults
            if "discovery" in saved:
                self._data["discovery"].update(saved["discovery"])
            if "credential_profiles" in saved:
                self._data["credential_profiles"] = saved["credential_profiles"]
            if "collection_profile" in saved:
                self._data["collection_profile"] = saved["collection_profile"]
            if "custom_groups" in saved:
                self._data["custom_groups"] = saved["custom_groups"]
            if "general" in saved:
                for key in _UI_FIELDS:
                    if key in saved["general"]:
                        self._data["general"][key] = saved["general"][key]

    def _save(self) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("app_settings", json.dumps(self._data)),
        )
        self._conn.commit()

    def update(self, data: dict[str, Any]) -> dict[str, Any]:
        result = super().update(data)
        self._save()
        return result

    def reset(self) -> dict[str, Any]:
        result = super().reset()
        self._save()
        return result


def make_settings_store(db_conn: sqlite3.Connection | None = None) -> SettingsStore:
    """Factory: SQLite store if connection provided, otherwise in-memory."""
    if db_conn is not None:
        return SQLiteSettingsStore(db_conn)
    return SettingsStore()
