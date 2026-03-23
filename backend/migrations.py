"""Lightweight SQLite schema migration framework.

Tracks schema versions in a ``schema_version`` table and applies
incremental migrations on startup. Automatically backs up the database
file before running any new migrations.

Usage:
    from backend.migrations import run_migrations

    conn = sqlite3.connect("netscope.db")
    run_migrations(conn, db_path)  # applies pending migrations + backup
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Migration definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Migration:
    """A single schema migration step."""

    version: int
    description: str
    up: str  # SQL to apply
    down: str  # SQL to revert (best-effort)


# ---------------------------------------------------------------------------
# Migration registry — append new migrations here
# ---------------------------------------------------------------------------

MIGRATIONS: Sequence[Migration] = [
    Migration(
        version=1,
        description="Initial schema — all tables from v0.2.0",
        up="""\
-- Core discovery tables
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    discovered_at TEXT NOT NULL,
    data         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS config_dumps (
    dump_id      TEXT PRIMARY KEY,
    device_id    TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    data         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discover_requests (
    session_id   TEXT PRIMARY KEY,
    data         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topology_diffs (
    diff_id           TEXT PRIMARY KEY,
    current_session_id TEXT NOT NULL,
    previous_session_id TEXT NOT NULL,
    computed_at       TEXT NOT NULL,
    data              TEXT NOT NULL
);

-- Alert tables
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id    TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    alert_id        TEXT PRIMARY KEY,
    rule_id         TEXT NOT NULL,
    triggered_at    TEXT NOT NULL,
    acknowledged_at TEXT,
    data            TEXT NOT NULL
);

-- Auth tables
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'viewer',
    created_at    TEXT NOT NULL,
    disabled      INTEGER NOT NULL DEFAULT 0,
    data          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id         TEXT PRIMARY KEY,
    key_hash   TEXT NOT NULL UNIQUE,
    label      TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    disabled   INTEGER NOT NULL DEFAULT 0,
    data       TEXT NOT NULL
);

-- Saved views
CREATE TABLE IF NOT EXISTS saved_views (
    view_id    TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data       TEXT NOT NULL
);

-- Full-text search (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    label,
    detail,
    session_id UNINDEXED,
    device_id  UNINDEXED,
    result_type UNINDEXED,
    tab         UNINDEXED
);

-- Audit records
CREATE TABLE IF NOT EXISTS audit_records (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    device_id   TEXT NOT NULL,
    device_ip   TEXT NOT NULL,
    operation   TEXT NOT NULL,
    status      TEXT NOT NULL,
    undo_of     TEXT,
    undone_by   TEXT,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_device ON audit_records(device_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_records(timestamp);

-- Playbooks
CREATE TABLE IF NOT EXISTS playbooks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    builtin     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    data        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playbook_executions (
    id            TEXT PRIMARY KEY,
    playbook_id   TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    overall_status TEXT NOT NULL,
    data          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pb_exec_playbook ON playbook_executions(playbook_id);
CREATE INDEX IF NOT EXISTS idx_pb_exec_ts ON playbook_executions(timestamp);

-- Settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
""",
        down="""\
DROP TABLE IF EXISTS settings;
DROP TABLE IF EXISTS playbook_executions;
DROP TABLE IF EXISTS playbooks;
DROP TABLE IF EXISTS audit_records;
DROP TABLE IF EXISTS search_index;
DROP TABLE IF EXISTS saved_views;
DROP TABLE IF EXISTS api_keys;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS alerts;
DROP TABLE IF EXISTS alert_rules;
DROP TABLE IF EXISTS topology_diffs;
DROP TABLE IF EXISTS discover_requests;
DROP TABLE IF EXISTS config_dumps;
DROP TABLE IF EXISTS sessions;
""",
    ),
    Migration(
        version=2,
        description="Add index on config_dumps.device_id for faster device lookups",
        up="CREATE INDEX IF NOT EXISTS idx_config_dumps_device ON config_dumps(device_id);",
        down="DROP INDEX IF EXISTS idx_config_dumps_device;",
    ),
]

# ---------------------------------------------------------------------------
# Version tracking
# ---------------------------------------------------------------------------

_VERSION_DDL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
"""


def get_current_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied migration version, or 0 if none."""
    conn.executescript(_VERSION_DDL)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] if row[0] is not None else 0


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def backup_database(db_path: Path) -> Path | None:
    """Create a timestamped backup of *db_path* before migration.

    Returns the backup path, or ``None`` if the file doesn't exist yet
    (fresh database — nothing to back up).
    """
    if not db_path.exists():
        return None
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_suffix(f".backup-{ts}.db")
    shutil.copy2(db_path, backup_path)
    logger.info("Database backup created: %s", backup_path)
    return backup_path


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------

# Track which db paths have already been migrated in this process to avoid
# re-running migrations on every _open_db() call (multiple stores share a path).
_migrated_paths: set[str] = set()


def run_migrations(
    conn: sqlite3.Connection,
    db_path: Path | None = None,
    *,
    migrations: Sequence[Migration] | None = None,
    force: bool = False,
) -> int:
    """Apply pending migrations to *conn*.

    Args:
        conn: Open SQLite connection.
        db_path: Path to the database file (used for backup and dedup).
                 Pass ``None`` for in-memory databases.
        migrations: Override the migration list (useful for testing).
        force: Skip the per-process dedup check.

    Returns:
        Number of migrations applied.
    """
    if migrations is None:
        migrations = MIGRATIONS

    # Per-process dedup: skip if we already migrated this path in this process
    path_key = str(db_path) if db_path else ":memory:"
    if not force and path_key in _migrated_paths:
        return 0

    current = get_current_version(conn)
    pending = [m for m in migrations if m.version > current]

    if not pending:
        _migrated_paths.add(path_key)
        return 0

    # Back up before applying any new migrations
    if db_path is not None:
        backup_database(db_path)

    for m in sorted(pending, key=lambda x: x.version):
        logger.info(
            "Applying migration %d: %s",
            m.version,
            m.description,
        )
        conn.executescript(m.up)
        conn.execute(
            "INSERT INTO schema_version (version, description, applied_at) VALUES (?, ?, ?)",
            (m.version, m.description, datetime.now(UTC).isoformat()),
        )
        conn.commit()

    applied = len(pending)
    logger.info(
        "Schema migrated from v%d to v%d (%d migration(s) applied)",
        current,
        current + applied,
        applied,
    )
    _migrated_paths.add(path_key)
    return applied


def rollback(
    conn: sqlite3.Connection,
    target_version: int = 0,
    *,
    migrations: Sequence[Migration] | None = None,
) -> int:
    """Roll back migrations down to *target_version* (exclusive).

    Returns the number of migrations rolled back.
    """
    if migrations is None:
        migrations = MIGRATIONS

    current = get_current_version(conn)
    to_rollback = sorted(
        [m for m in migrations if target_version < m.version <= current],
        key=lambda x: x.version,
        reverse=True,
    )

    for m in to_rollback:
        logger.info("Rolling back migration %d: %s", m.version, m.description)
        conn.executescript(m.down)
        conn.execute("DELETE FROM schema_version WHERE version = ?", (m.version,))
        conn.commit()

    return len(to_rollback)


def reset_migrated_paths() -> None:
    """Clear the per-process dedup cache. Useful for testing."""
    _migrated_paths.clear()
