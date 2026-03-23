"""Tests for database backup/restore and session import/export endpoints."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.main import app
from backend.models import Device, DeviceStatus, SavedView, TopologyResult
from backend.store import store, view_store


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.fixture
async def sample_session():
    result = TopologyResult(
        session_id="backup-test-001",
        discovered_at=datetime.now(UTC),
        devices=[
            Device(
                id="R1",
                hostname="R1",
                mgmt_ip="10.0.0.1",
                platform="C9200L",
                status=DeviceStatus.OK,
            ),
        ],
        links=[],
        failures=[],
    )
    await store.save(result)
    return result


@pytest.fixture
async def sample_session_with_view(sample_session):
    view = SavedView(
        view_id="view-001",
        session_id=sample_session.session_id,
        name="Test View",
        description="",
        is_default=False,
        zoom=1.0,
        pan_x=0.0,
        pan_y=0.0,
        node_positions=[],
        protocol_filter="all",
        vlan_filter=None,
        annotations=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await view_store.save(view)
    return sample_session, view


# ---------------------------------------------------------------------------
# Session Export / Import
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_session_bundle(client: AsyncClient, sample_session: TopologyResult):
    resp = await client.get(f"/sessions/{sample_session.session_id}/export-bundle")
    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]

    bundle = resp.json()
    assert bundle["format"] == "netscope-session-bundle"
    assert bundle["version"] == 1
    assert bundle["session"]["session_id"] == sample_session.session_id
    assert len(bundle["session"]["devices"]) == 1


@pytest.mark.asyncio
async def test_export_session_bundle_includes_views(client: AsyncClient, sample_session_with_view):
    session, view = sample_session_with_view
    resp = await client.get(f"/sessions/{session.session_id}/export-bundle")
    assert resp.status_code == 200
    bundle = resp.json()
    assert len(bundle["saved_views"]) == 1
    assert bundle["saved_views"][0]["view_id"] == view.view_id


@pytest.mark.asyncio
async def test_export_session_not_found(client: AsyncClient):
    resp = await client.get("/sessions/nonexistent-id/export-bundle")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_session_bundle(client: AsyncClient, sample_session: TopologyResult):
    # First export
    resp = await client.get(f"/sessions/{sample_session.session_id}/export-bundle")
    bundle_data = resp.content

    # Modify session_id so it imports as new
    bundle = json.loads(bundle_data)
    bundle["session"]["session_id"] = "imported-session-002"
    modified = json.dumps(bundle).encode()

    resp = await client.post(
        "/sessions/import-bundle",
        files={"file": ("session.json", modified, "application/json")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "imported"
    assert data["session_id"] == "imported-session-002"
    assert data["device_count"] == 1

    # Verify session was saved
    saved = store.get("imported-session-002")
    assert saved is not None
    assert len(saved.devices) == 1


@pytest.mark.asyncio
async def test_import_invalid_json(client: AsyncClient):
    resp = await client.post(
        "/sessions/import-bundle",
        files={"file": ("bad.json", b"not-json", "application/json")},
    )
    assert resp.status_code == 400
    assert "Invalid JSON" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_import_wrong_format(client: AsyncClient):
    resp = await client.post(
        "/sessions/import-bundle",
        files={"file": ("bad.json", b'{"format":"other"}', "application/json")},
    )
    assert resp.status_code == 400
    assert "format marker" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Database Backup / Restore
# ---------------------------------------------------------------------------


@pytest.fixture
def _patch_db_path():
    """Context manager to temporarily set/unset settings.db_path."""
    original = settings.db_path

    class _Ctx:
        def set(self, value: str | None) -> None:
            object.__setattr__(settings, "db_path", value)

        def restore(self) -> None:
            object.__setattr__(settings, "db_path", original)

    ctx = _Ctx()
    yield ctx
    ctx.restore()


@pytest.mark.asyncio
async def test_backup_requires_db_path(client: AsyncClient, _patch_db_path):
    """Backup endpoint returns 422 when not in SQLite mode."""
    _patch_db_path.set(None)
    resp = await client.get("/backup/database")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_restore_requires_db_path(client: AsyncClient, _patch_db_path):
    """Restore endpoint returns 422 when not in SQLite mode."""
    _patch_db_path.set(None)
    resp = await client.post(
        "/backup/restore",
        files={"file": ("backup.db", b"x" * 200, "application/octet-stream")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_backup_and_restore_roundtrip(client: AsyncClient, _patch_db_path):
    """Full roundtrip: create temp DB, backup, then restore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        # Create a minimal valid SQLite database with sessions table
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions"
            " (session_id TEXT PRIMARY KEY, discovered_at TEXT, data TEXT)"
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?)",
            ("s1", datetime.now(UTC).isoformat(), '{"session_id":"s1"}'),
        )
        conn.commit()
        conn.close()

        _patch_db_path.set(db_path)

        # Backup
        resp = await client.get("/backup/database")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        backup_data = resp.content
        assert len(backup_data) > 0

        # Now restore using the same backup data
        resp = await client.post(
            "/backup/restore",
            files={"file": ("backup.db", backup_data, "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "restored"


@pytest.mark.asyncio
async def test_restore_rejects_invalid_file(client: AsyncClient, _patch_db_path):
    """Restore rejects files that are not valid SQLite databases."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        Path(db_path).touch()
        _patch_db_path.set(db_path)

        resp = await client.post(
            "/backup/restore",
            files={"file": ("bad.db", b"not-a-database" * 20, "application/octet-stream")},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_restore_rejects_missing_tables(client: AsyncClient, _patch_db_path):
    """Restore rejects databases missing required tables."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        Path(db_path).touch()

        # Create a valid SQLite DB but without sessions table
        empty_db = Path(tmpdir) / "empty.db"
        conn = sqlite3.connect(str(empty_db))
        conn.execute("CREATE TABLE other (id TEXT)")
        conn.commit()
        conn.close()
        upload_data = empty_db.read_bytes()

        _patch_db_path.set(db_path)

        resp = await client.post(
            "/backup/restore",
            files={"file": ("empty.db", upload_data, "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "missing tables" in resp.json()["detail"]
