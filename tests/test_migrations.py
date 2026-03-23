"""Tests for the schema migration framework."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.migrations import (
    Migration,
    backup_database,
    get_current_version,
    reset_migrated_paths,
    rollback,
    run_migrations,
)


@pytest.fixture(autouse=True)
def _clean_dedup() -> None:
    """Reset per-process dedup cache between tests."""
    reset_migrated_paths()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(db_path))


# ---------------------------------------------------------------------------
# Simple test migrations (not the real ones)
# ---------------------------------------------------------------------------

_TEST_MIGRATIONS = [
    Migration(
        version=1,
        description="Create users table",
        up="CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL);",
        down="DROP TABLE IF EXISTS users;",
    ),
    Migration(
        version=2,
        description="Add email column",
        up="ALTER TABLE users ADD COLUMN email TEXT;",
        down=(
            "CREATE TABLE users_backup (id TEXT PRIMARY KEY, name TEXT NOT NULL);"
            "INSERT INTO users_backup SELECT id, name FROM users;"
            "DROP TABLE users;"
            "ALTER TABLE users_backup RENAME TO users;"
        ),
    ),
]


class TestGetCurrentVersion:
    def test_fresh_database(self, conn: sqlite3.Connection) -> None:
        assert get_current_version(conn) == 0

    def test_after_migration(self, conn: sqlite3.Connection, db_path: Path) -> None:
        run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS[:1], force=True)
        assert get_current_version(conn) == 1


class TestRunMigrations:
    def test_applies_all_pending(self, conn: sqlite3.Connection, db_path: Path) -> None:
        applied = run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS, force=True)
        assert applied == 2
        assert get_current_version(conn) == 2
        # Verify tables exist
        conn.execute("INSERT INTO users (id, name, email) VALUES ('1', 'alice', 'a@b.com')")

    def test_incremental(self, conn: sqlite3.Connection, db_path: Path) -> None:
        run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS[:1], force=True)
        assert get_current_version(conn) == 1
        # Apply second migration
        applied = run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS, force=True)
        assert applied == 1
        assert get_current_version(conn) == 2

    def test_no_pending(self, conn: sqlite3.Connection, db_path: Path) -> None:
        run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS, force=True)
        applied = run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS, force=True)
        assert applied == 0

    def test_dedup_skips_same_path(self, conn: sqlite3.Connection, db_path: Path) -> None:
        run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS)
        # Second call without force should be deduped
        applied = run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS)
        assert applied == 0

    def test_force_ignores_dedup(self, conn: sqlite3.Connection, db_path: Path) -> None:
        run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS[:1])
        applied = run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS, force=True)
        assert applied == 1


class TestRollback:
    def test_rollback_all(self, conn: sqlite3.Connection, db_path: Path) -> None:
        run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS, force=True)
        rolled = rollback(conn, target_version=0, migrations=_TEST_MIGRATIONS)
        assert rolled == 2
        assert get_current_version(conn) == 0

    def test_rollback_partial(self, conn: sqlite3.Connection, db_path: Path) -> None:
        run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS, force=True)
        rolled = rollback(conn, target_version=1, migrations=_TEST_MIGRATIONS)
        assert rolled == 1
        assert get_current_version(conn) == 1

    def test_rollback_noop(self, conn: sqlite3.Connection, db_path: Path) -> None:
        run_migrations(conn, db_path, migrations=_TEST_MIGRATIONS[:1], force=True)
        rolled = rollback(conn, target_version=1, migrations=_TEST_MIGRATIONS)
        assert rolled == 0


class TestBackup:
    def test_backup_creates_file(self, db_path: Path) -> None:
        # Create a database first
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.commit()
        conn.close()

        backup_path = backup_database(db_path)
        assert backup_path is not None
        assert backup_path.exists()
        assert ".backup-" in backup_path.name

    def test_backup_nonexistent(self, tmp_path: Path) -> None:
        result = backup_database(tmp_path / "no-such.db")
        assert result is None


class TestRealMigrations:
    """Test that the actual production migrations apply cleanly."""

    def test_production_migrations_apply(self, db_path: Path) -> None:
        """The real MIGRATIONS list applies to a fresh database without error."""
        from backend.migrations import MIGRATIONS

        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        applied = run_migrations(conn, db_path, migrations=MIGRATIONS, force=True)
        assert applied == len(MIGRATIONS)
        assert get_current_version(conn) == MIGRATIONS[-1].version

        # Verify key tables exist by inserting test data
        conn.execute(
            "INSERT INTO sessions (session_id, discovered_at, data)"
            " VALUES ('s1', '2024-01-01', '{}')"
        )
        conn.execute(
            "INSERT INTO audit_records"
            " (id, timestamp, device_id, device_ip, operation, status, data)"
            " VALUES ('a1', '2024-01-01', 'd1', '10.0.0.1', 'vlan', 'success', '{}')"
        )
        conn.execute(
            "INSERT INTO playbooks (id, title, category, created_at, data)"
            " VALUES ('p1', 'Test', 'test', '2024-01-01', '{}')"
        )
        conn.execute("INSERT INTO settings (key, value) VALUES ('k', 'v')")
        conn.commit()
        conn.close()

    def test_production_migrations_rollback(self, db_path: Path) -> None:
        """The real MIGRATIONS list can be rolled back cleanly."""
        from backend.migrations import MIGRATIONS

        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn, db_path, migrations=MIGRATIONS, force=True)
        rolled = rollback(conn, target_version=0, migrations=MIGRATIONS)
        assert rolled == len(MIGRATIONS)
        assert get_current_version(conn) == 0
        conn.close()

    def test_existing_db_upgrades(self, db_path: Path) -> None:
        """Simulates upgrading a pre-migration database.

        Creates tables manually (as the old code did), then runs migrations.
        The IF NOT EXISTS clauses ensure no errors on upgrade.
        """
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        # Create a table that already exists in migration v1
        conn.execute(
            "CREATE TABLE sessions ("
            "session_id TEXT PRIMARY KEY, discovered_at TEXT NOT NULL, data TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO sessions (session_id, discovered_at, data)"
            " VALUES ('existing', '2024-01-01', '{}')"
        )
        conn.commit()

        from backend.migrations import MIGRATIONS

        applied = run_migrations(conn, db_path, migrations=MIGRATIONS, force=True)
        assert applied == len(MIGRATIONS)

        # Existing data is preserved
        row = conn.execute("SELECT data FROM sessions WHERE session_id = 'existing'").fetchone()
        assert row is not None
        conn.close()

    def test_backup_before_migration(self, db_path: Path) -> None:
        """Backup is created when migrating an existing database."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dummy (x TEXT)")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(str(db_path))
        from backend.migrations import MIGRATIONS

        run_migrations(conn, db_path, migrations=MIGRATIONS, force=True)
        conn.close()

        backups = list(db_path.parent.glob("*.backup-*.db"))
        assert len(backups) >= 1


class TestOpenDbIntegration:
    """Test that _open_db runs migrations correctly."""

    def test_open_db_creates_tables(self, tmp_path: Path) -> None:
        from backend.store_sqlite import _open_db

        db = tmp_path / "integration.db"
        conn = _open_db(db)
        # Should be able to query any table created by migrations
        conn.execute("SELECT count(*) FROM sessions")
        conn.execute("SELECT count(*) FROM audit_records")
        conn.execute("SELECT count(*) FROM playbooks")
        conn.execute("SELECT count(*) FROM settings")
        conn.close()
