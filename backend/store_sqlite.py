"""SQLite-backed session and config-dump stores.

Activated when NETSCOPE_DB_PATH is set. Uses stdlib sqlite3 with WAL mode
for concurrent read access. Full Pydantic models are stored as JSON blobs.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.credential_vault import CredentialVault

from backend.migrations import run_migrations
from backend.models import (
    Alert,
    AlertRule,
    ConfigDump,
    DiscoverRequest,
    SavedView,
    SnapshotMeta,
    TopologyDiff,
    TopologyResult,
)


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database and apply pending migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    run_migrations(conn, db_path)
    return conn


class SQLiteSessionStore:
    """SQLite-backed SessionStore with the same interface as the in-memory store."""

    def __init__(self, db_path: Path) -> None:
        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()

    async def save(self, result: TopologyResult) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO sessions"
                " (session_id, discovered_at, data) VALUES (?, ?, ?)",
                (
                    result.session_id,
                    result.discovered_at.isoformat(),
                    result.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get(self, session_id: str) -> TopologyResult | None:
        row = self._conn.execute(
            "SELECT data FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return TopologyResult.model_validate_json(row[0])

    def list_all(self) -> list[TopologyResult]:
        rows = self._conn.execute(
            "SELECT data FROM sessions ORDER BY discovered_at DESC"
        ).fetchall()
        return [TopologyResult.model_validate_json(r[0]) for r in rows]

    def list_meta(self) -> list[SnapshotMeta]:
        """Return lightweight snapshot metadata without deserialising full JSON blobs."""
        rows = self._conn.execute(
            "SELECT session_id, discovered_at,"
            " json_array_length(json_extract(data, '$.devices')),"
            " json_array_length(json_extract(data, '$.links')),"
            " json_array_length(json_extract(data, '$.failures'))"
            " FROM sessions ORDER BY discovered_at DESC"
        ).fetchall()
        return [
            SnapshotMeta(
                session_id=r[0],
                discovered_at=datetime.fromisoformat(r[1]),
                device_count=r[2] or 0,
                link_count=r[3] or 0,
                failure_count=r[4] or 0,
            )
            for r in rows
        ]


def cleanup_old_snapshots(conn: sqlite3.Connection, retention_days: int) -> int:
    """Delete sessions/snapshots older than *retention_days*.

    Returns the number of rows deleted. No-op when *retention_days* is 0.
    """
    if retention_days <= 0:
        return 0
    cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
    cur = conn.execute("DELETE FROM sessions WHERE discovered_at < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


class SQLiteConfigDumpStore:
    """SQLite-backed ConfigDumpStore with optional Fernet encryption."""

    def __init__(self, db_path: Path, vault: CredentialVault | None = None) -> None:
        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()
        self._vault = vault

    async def save(self, dump: ConfigDump) -> None:
        async with self._lock:
            data = dump.model_dump_json()
            if self._vault is not None:
                data = self._vault.encrypt(data)
            self._conn.execute(
                "INSERT OR REPLACE INTO config_dumps"
                " (dump_id, device_id, requested_at, data) VALUES (?, ?, ?, ?)",
                (dump.dump_id, dump.device_id, dump.dumped_at.isoformat(), data),
            )
            self._conn.commit()

    def _decrypt_row(self, raw: str) -> str:
        if self._vault is None:
            return raw
        try:
            return self._vault.decrypt(raw)
        except Exception:
            return raw  # Legacy unencrypted row

    def get(self, dump_id: str) -> ConfigDump | None:
        row = self._conn.execute(
            "SELECT data FROM config_dumps WHERE dump_id = ?", (dump_id,)
        ).fetchone()
        if row is None:
            return None
        return ConfigDump.model_validate_json(self._decrypt_row(row[0]))

    def list_all(self) -> list[ConfigDump]:
        rows = self._conn.execute(
            "SELECT data FROM config_dumps ORDER BY requested_at DESC"
        ).fetchall()
        return [ConfigDump.model_validate_json(self._decrypt_row(r[0])) for r in rows]

    def list_for_device(self, device_id: str) -> list[ConfigDump]:
        rows = self._conn.execute(
            "SELECT data FROM config_dumps WHERE device_id = ? ORDER BY requested_at DESC",
            (device_id,),
        ).fetchall()
        return [ConfigDump.model_validate_json(self._decrypt_row(r[0])) for r in rows]


class SQLiteDiscoverRequestStore:
    """Persists the original DiscoverRequest for each session so it can be re-run.

    When a ``CredentialVault`` is provided, the JSON blob is encrypted before
    writing and decrypted on read. Legacy unencrypted rows are handled
    gracefully (decrypt failure falls back to raw JSON parsing).
    """

    def __init__(self, db_path: Path, vault: CredentialVault | None = None) -> None:
        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()
        self._vault = vault

    async def save(self, session_id: str, req: DiscoverRequest) -> None:
        data = req.model_dump_json()
        if self._vault is not None:
            data = self._vault.encrypt(data)
        async with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO discover_requests (session_id, data) VALUES (?, ?)",
                (session_id, data),
            )
            self._conn.commit()

    def get(self, session_id: str) -> DiscoverRequest | None:
        row = self._conn.execute(
            "SELECT data FROM discover_requests WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        data: str = row[0]
        if self._vault is not None:
            try:
                data = self._vault.decrypt(data)
            except Exception:
                pass  # Fall back to unencrypted for legacy data
        return DiscoverRequest.model_validate_json(data)


class SQLiteDiffStore:
    """Persists computed TopologyDiff objects."""

    def __init__(self, db_path: Path) -> None:
        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()

    async def save(self, diff: TopologyDiff) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO topology_diffs"
                " (diff_id, current_session_id, previous_session_id, computed_at, data)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    diff.diff_id,
                    diff.current_session_id,
                    diff.previous_session_id,
                    diff.computed_at.isoformat(),
                    diff.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get_by_sessions(
        self, current_session_id: str, previous_session_id: str
    ) -> TopologyDiff | None:
        row = self._conn.execute(
            "SELECT data FROM topology_diffs"
            " WHERE current_session_id = ? AND previous_session_id = ?",
            (current_session_id, previous_session_id),
        ).fetchone()
        if row is None:
            return None
        return TopologyDiff.model_validate_json(row[0])

    def list_for_session(self, session_id: str) -> list[TopologyDiff]:
        rows = self._conn.execute(
            "SELECT data FROM topology_diffs"
            " WHERE current_session_id = ? ORDER BY computed_at DESC",
            (session_id,),
        ).fetchall()
        return [TopologyDiff.model_validate_json(r[0]) for r in rows]


class SQLiteAlertRuleStore:
    """Persists AlertRule objects."""

    def __init__(self, db_path: Path) -> None:
        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()

    async def save(self, rule: AlertRule) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO alert_rules (rule_id, created_at, data) VALUES (?, ?, ?)",
                (rule.rule_id, rule.created_at.isoformat(), rule.model_dump_json()),
            )
            self._conn.commit()

    def get(self, rule_id: str) -> AlertRule | None:
        row = self._conn.execute(
            "SELECT data FROM alert_rules WHERE rule_id = ?", (rule_id,)
        ).fetchone()
        if row is None:
            return None
        return AlertRule.model_validate_json(row[0])

    def list_all(self) -> list[AlertRule]:
        rows = self._conn.execute(
            "SELECT data FROM alert_rules ORDER BY created_at DESC"
        ).fetchall()
        return [AlertRule.model_validate_json(r[0]) for r in rows]

    async def delete(self, rule_id: str) -> bool:
        async with self._lock:
            cur = self._conn.execute("DELETE FROM alert_rules WHERE rule_id = ?", (rule_id,))
            self._conn.commit()
            return cur.rowcount > 0


class SQLiteAlertStore:
    """Persists fired Alert objects (history)."""

    def __init__(self, db_path: Path) -> None:
        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()

    async def save(self, alert: Alert) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO alerts"
                " (alert_id, rule_id, triggered_at, acknowledged_at, data)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    alert.alert_id,
                    alert.rule_id,
                    alert.triggered_at.isoformat(),
                    alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    alert.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get(self, alert_id: str) -> Alert | None:
        row = self._conn.execute(
            "SELECT data FROM alerts WHERE alert_id = ?", (alert_id,)
        ).fetchone()
        if row is None:
            return None
        return Alert.model_validate_json(row[0])

    def list_all(self, limit: int = 200) -> list[Alert]:
        rows = self._conn.execute(
            "SELECT data FROM alerts ORDER BY triggered_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Alert.model_validate_json(r[0]) for r in rows]

    async def acknowledge(self, alert_id: str, acked: bool) -> Alert | None:
        async with self._lock:
            alert = self.get(alert_id)
            if alert is None:
                return None
            alert = alert.model_copy(
                update={
                    "acknowledged_at": datetime.now(UTC) if acked else None,
                }
            )
            self._conn.execute(
                "UPDATE alerts SET acknowledged_at = ?, data = ? WHERE alert_id = ?",
                (
                    alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    alert.model_dump_json(),
                    alert_id,
                ),
            )
            self._conn.commit()
            return alert


class SQLiteSavedViewStore:
    """Persists SavedView objects."""

    def __init__(self, db_path: Path) -> None:
        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()

    async def save(self, view: SavedView) -> None:
        async with self._lock:
            # If setting as default, clear other defaults for the same session
            if view.is_default:
                self._conn.execute(
                    "UPDATE saved_views SET is_default = 0,"
                    " data = json_set(data, '$.is_default', json('false'))"
                    " WHERE session_id = ? AND view_id != ?",
                    (view.session_id, view.view_id),
                )
            self._conn.execute(
                "INSERT OR REPLACE INTO saved_views"
                " (view_id, session_id, name, is_default, created_at, updated_at, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    view.view_id,
                    view.session_id,
                    view.name,
                    1 if view.is_default else 0,
                    view.created_at.isoformat(),
                    view.updated_at.isoformat(),
                    view.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get(self, view_id: str) -> SavedView | None:
        row = self._conn.execute(
            "SELECT data FROM saved_views WHERE view_id = ?", (view_id,)
        ).fetchone()
        if row is None:
            return None
        return SavedView.model_validate_json(row[0])

    def list_all(self, session_id: str | None = None) -> list[SavedView]:
        if session_id:
            rows = self._conn.execute(
                "SELECT data FROM saved_views WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data FROM saved_views ORDER BY created_at DESC"
            ).fetchall()
        return [SavedView.model_validate_json(r[0]) for r in rows]

    async def delete(self, view_id: str) -> bool:
        async with self._lock:
            cur = self._conn.execute("DELETE FROM saved_views WHERE view_id = ?", (view_id,))
            self._conn.commit()
            return cur.rowcount > 0

    async def rename(self, view_id: str, name: str) -> SavedView | None:
        async with self._lock:
            view = self.get(view_id)
            if view is None:
                return None
            view = view.model_copy(update={"name": name, "updated_at": datetime.now(UTC)})
            self._conn.execute(
                "UPDATE saved_views SET name = ?, updated_at = ?, data = ? WHERE view_id = ?",
                (name, view.updated_at.isoformat(), view.model_dump_json(), view_id),
            )
            self._conn.commit()
            return view
