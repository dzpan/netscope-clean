"""Tests for snapshot storage, retrieval, and retention cleanup."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.models import Device, DeviceStatus, Link, TopologyResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    session_id: str = "s1",
    days_ago: int = 0,
    device_count: int = 1,
) -> TopologyResult:
    discovered_at = datetime.now(UTC) - timedelta(days=days_ago)
    devices = [
        Device(
            id=f"SW-{i}",
            hostname=f"SW-{i}",
            mgmt_ip=f"10.0.0.{i + 1}",
            status=DeviceStatus.OK,
        )
        for i in range(device_count)
    ]
    links = (
        [
            Link(
                source="SW-0",
                target="SW-1",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet0/1",
                protocol="CDP",
            )
        ]
        if device_count > 1
        else []
    )
    return TopologyResult(
        session_id=session_id,
        discovered_at=discovered_at,
        devices=devices,
        links=links,
        failures=[],
    )


# ---------------------------------------------------------------------------
# SQLite list_meta
# ---------------------------------------------------------------------------


class TestSQLiteListMeta:
    def setup_method(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.db"
        from backend.store_sqlite import SQLiteSessionStore

        self.store = SQLiteSessionStore(self._db_path)

    def test_list_meta_empty(self) -> None:
        assert self.store.list_meta() == []

    def test_list_meta_counts(self) -> None:
        asyncio.run(self.store.save(_make_result("s1", device_count=3)))
        asyncio.run(self.store.save(_make_result("s2", device_count=1)))
        meta = self.store.list_meta()
        assert len(meta) == 2
        # Most recent first — both were saved at "now", same order as insertion
        ids = {m.session_id for m in meta}
        assert ids == {"s1", "s2"}
        for m in meta:
            if m.session_id == "s1":
                assert m.device_count == 3
                assert m.link_count == 1  # SW-0 → SW-1 link (device_count > 1)
            else:
                assert m.device_count == 1
                assert m.link_count == 0

    def test_list_meta_with_links(self) -> None:
        asyncio.run(self.store.save(_make_result("s1", device_count=2)))
        meta = self.store.list_meta()
        assert len(meta) == 1
        assert meta[0].link_count == 1


# ---------------------------------------------------------------------------
# Retention cleanup
# ---------------------------------------------------------------------------


class TestCleanupOldSnapshots:
    def setup_method(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.db"
        from backend.store_sqlite import SQLiteSessionStore, _open_db

        self.store = SQLiteSessionStore(self._db_path)
        self._conn = _open_db(self._db_path)

    def test_no_op_when_retention_zero(self) -> None:
        from backend.store_sqlite import cleanup_old_snapshots

        asyncio.run(self.store.save(_make_result("s1", days_ago=100)))
        deleted = cleanup_old_snapshots(self._conn, 0)
        assert deleted == 0
        assert self.store.get("s1") is not None

    def test_deletes_old_snapshots(self) -> None:
        from backend.store_sqlite import cleanup_old_snapshots

        asyncio.run(self.store.save(_make_result("old", days_ago=100)))
        asyncio.run(self.store.save(_make_result("recent", days_ago=5)))
        deleted = cleanup_old_snapshots(self._conn, 30)
        assert deleted == 1
        assert self.store.get("old") is None
        assert self.store.get("recent") is not None

    def test_keeps_snapshots_within_retention(self) -> None:
        from backend.store_sqlite import cleanup_old_snapshots

        asyncio.run(self.store.save(_make_result("a", days_ago=10)))
        asyncio.run(self.store.save(_make_result("b", days_ago=20)))
        deleted = cleanup_old_snapshots(self._conn, 30)
        assert deleted == 0
        assert len(self.store.list_all()) == 2

    def test_deletes_multiple_old(self) -> None:
        from backend.store_sqlite import cleanup_old_snapshots

        asyncio.run(self.store.save(_make_result("x1", days_ago=91)))
        asyncio.run(self.store.save(_make_result("x2", days_ago=95)))
        asyncio.run(self.store.save(_make_result("x3", days_ago=1)))
        deleted = cleanup_old_snapshots(self._conn, 90)
        assert deleted == 2
        assert len(self.store.list_all()) == 1


# ---------------------------------------------------------------------------
# Snapshot API endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
async def in_memory_store_with_sessions() -> TopologyResult:
    """Populate the in-memory store with two sessions and return the newer one."""
    from backend.store import store

    r1 = _make_result("snap-old", device_count=1)
    r2 = _make_result("snap-new", device_count=3)
    await store.save(r1)
    await store.save(r2)
    return r2


@pytest.fixture
async def client():
    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.mark.asyncio
async def test_list_snapshots_empty(client):
    """GET /snapshots returns an empty list when no sessions exist."""
    import backend.store as _store_module
    from backend.store import SessionStore

    original = _store_module.store
    _store_module.store = SessionStore()
    try:
        resp = await client.get("/snapshots")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _store_module.store = original


@pytest.mark.asyncio
async def test_list_snapshots(client, in_memory_store_with_sessions):
    resp = await client.get("/snapshots")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = {d["session_id"] for d in data}
    assert "snap-old" in ids
    assert "snap-new" in ids
    newer = next(d for d in data if d["session_id"] == "snap-new")
    assert newer["device_count"] == 3


@pytest.mark.asyncio
async def test_get_snapshot_found(client, in_memory_store_with_sessions):
    resp = await client.get("/snapshots/snap-new")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "snap-new"
    assert len(data["devices"]) == 3


@pytest.mark.asyncio
async def test_get_snapshot_not_found(client):
    resp = await client.get("/snapshots/does-not-exist")
    assert resp.status_code == 404
