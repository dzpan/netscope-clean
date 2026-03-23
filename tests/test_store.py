"""Tests for both in-memory and SQLite store backends."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.credential_vault import CredentialVault
from backend.models import ConfigDump, Device, DeviceStatus, Link, TopologyResult
from backend.store_sqlite import SQLiteConfigDumpStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_result(session_id: str = "s1") -> TopologyResult:
    return TopologyResult(
        session_id=session_id,
        discovered_at=datetime.now(UTC),
        devices=[
            Device(id="SW1", hostname="SW1", mgmt_ip="10.0.0.1", status=DeviceStatus.OK),
        ],
        links=[
            Link(
                source="SW1",
                target="SW2",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet0/1",
                protocol="CDP",
            )
        ],
        failures=[],
    )


def _make_dump(dump_id: str = "d1", device_id: str = "SW1") -> ConfigDump:
    return ConfigDump(
        dump_id=dump_id,
        device_id=device_id,
        device_ip="10.0.0.1",
        dumped_at=datetime.now(UTC),
        commands=[],
    )


# ---------------------------------------------------------------------------
# In-memory SessionStore
# ---------------------------------------------------------------------------


class TestInMemorySessionStore:
    def setup_method(self) -> None:
        from backend.store import SessionStore

        self.store = SessionStore(max_sessions=3)

    def test_save_and_get(self) -> None:
        r = _make_result("sess-1")
        asyncio.run(self.store.save(r))
        got = self.store.get("sess-1")
        assert got is not None
        assert got.session_id == "sess-1"
        assert len(got.devices) == 1

    def test_get_missing(self) -> None:
        assert self.store.get("nope") is None

    def test_list_all_ordered(self) -> None:
        for i in range(3):
            asyncio.run(self.store.save(_make_result(f"s{i}")))
        all_sessions = self.store.list_all()
        assert len(all_sessions) == 3
        # Most recent first
        assert all_sessions[0].session_id == "s2"

    def test_lru_eviction(self) -> None:
        for i in range(4):
            asyncio.run(self.store.save(_make_result(f"s{i}")))
        all_sessions = self.store.list_all()
        assert len(all_sessions) == 3
        # Oldest (s0) should be evicted
        assert self.store.get("s0") is None
        assert self.store.get("s1") is not None


# ---------------------------------------------------------------------------
# In-memory ConfigDumpStore
# ---------------------------------------------------------------------------


class TestInMemoryConfigDumpStore:
    def setup_method(self) -> None:
        from backend.store import ConfigDumpStore

        self.store = ConfigDumpStore(max_dumps=3)

    def test_save_and_get(self) -> None:
        d = _make_dump("d1", "SW1")
        asyncio.run(self.store.save(d))
        got = self.store.get("d1")
        assert got is not None
        assert got.dump_id == "d1"

    def test_list_for_device(self) -> None:
        asyncio.run(self.store.save(_make_dump("d1", "SW1")))
        asyncio.run(self.store.save(_make_dump("d2", "SW2")))
        asyncio.run(self.store.save(_make_dump("d3", "SW1")))
        sw1_dumps = self.store.list_for_device("SW1")
        assert len(sw1_dumps) == 2
        assert all(d.device_id == "SW1" for d in sw1_dumps)


# ---------------------------------------------------------------------------
# SQLite SessionStore
# ---------------------------------------------------------------------------


class TestSQLiteSessionStore:
    def setup_method(self, tmp_path_factory: pytest.TempPathFactory | None = None) -> None:
        # Use a temp file
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.db"
        from backend.store_sqlite import SQLiteSessionStore

        self.store = SQLiteSessionStore(self._db_path)

    def test_save_and_get(self) -> None:
        r = _make_result("sqlite-sess-1")
        asyncio.run(self.store.save(r))
        got = self.store.get("sqlite-sess-1")
        assert got is not None
        assert got.session_id == "sqlite-sess-1"
        assert len(got.devices) == 1
        assert len(got.links) == 1

    def test_get_missing(self) -> None:
        assert self.store.get("nope") is None

    def test_list_all(self) -> None:
        for i in range(3):
            asyncio.run(self.store.save(_make_result(f"sq{i}")))
        all_sessions = self.store.list_all()
        assert len(all_sessions) == 3

    def test_overwrite_on_same_id(self) -> None:
        r1 = _make_result("dup")
        asyncio.run(self.store.save(r1))
        asyncio.run(self.store.save(r1))
        assert len(self.store.list_all()) == 1

    def test_persistence_across_instances(self) -> None:
        """Data saved in one instance is readable by a new instance on the same file."""
        from backend.store_sqlite import SQLiteSessionStore

        r = _make_result("persist-test")
        asyncio.run(self.store.save(r))

        store2 = SQLiteSessionStore(self._db_path)
        got = store2.get("persist-test")
        assert got is not None
        assert got.session_id == "persist-test"


# ---------------------------------------------------------------------------
# SQLite ConfigDumpStore
# ---------------------------------------------------------------------------


class TestSQLiteConfigDumpStore:
    def setup_method(self) -> None:
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.db"
        from backend.store_sqlite import SQLiteConfigDumpStore

        self.store = SQLiteConfigDumpStore(self._db_path)

    def test_save_and_get(self) -> None:
        d = _make_dump("sq-d1", "SW1")
        asyncio.run(self.store.save(d))
        got = self.store.get("sq-d1")
        assert got is not None
        assert got.dump_id == "sq-d1"

    def test_list_for_device(self) -> None:
        asyncio.run(self.store.save(_make_dump("a1", "SW1")))
        asyncio.run(self.store.save(_make_dump("a2", "SW2")))
        asyncio.run(self.store.save(_make_dump("a3", "SW1")))
        sw1_dumps = self.store.list_for_device("SW1")
        assert len(sw1_dumps) == 2
        assert all(d.device_id == "SW1" for d in sw1_dumps)

    def test_list_all(self) -> None:
        asyncio.run(self.store.save(_make_dump("b1")))
        asyncio.run(self.store.save(_make_dump("b2")))
        assert len(self.store.list_all()) == 2


class TestEncryptedConfigDumpStore:
    """SQLiteConfigDumpStore with vault encrypts data at rest."""

    @pytest.fixture()
    def encrypted_store(self, tmp_path: Path) -> SQLiteConfigDumpStore:
        vault = CredentialVault("test-encryption-key")
        return SQLiteConfigDumpStore(tmp_path / "test.db", vault=vault)

    async def test_encrypted_round_trip(self, encrypted_store: SQLiteConfigDumpStore) -> None:
        dump = _make_dump("enc-d1", "SW1")
        await encrypted_store.save(dump)
        loaded = encrypted_store.get("enc-d1")
        assert loaded is not None
        assert loaded.dump_id == "enc-d1"
        assert loaded.device_id == "SW1"

    async def test_encrypted_data_not_plaintext_in_db(
        self, encrypted_store: SQLiteConfigDumpStore
    ) -> None:
        dump = _make_dump("enc-d2", "SW1")
        await encrypted_store.save(dump)
        row = encrypted_store._conn.execute(
            "SELECT data FROM config_dumps WHERE dump_id = ?", ("enc-d2",)
        ).fetchone()
        assert row is not None
        import json

        with pytest.raises(json.JSONDecodeError):
            json.loads(row[0])

    async def test_legacy_unencrypted_rows_still_readable(self, tmp_path: Path) -> None:
        from backend.store_sqlite import SQLiteConfigDumpStore

        plain_store = SQLiteConfigDumpStore(tmp_path / "legacy.db")
        dump = _make_dump("legacy-d1", "SW1")
        await plain_store.save(dump)

        vault = CredentialVault("test-encryption-key")
        enc_store = SQLiteConfigDumpStore(tmp_path / "legacy.db", vault=vault)
        loaded = enc_store.get("legacy-d1")
        assert loaded is not None
        assert loaded.dump_id == "legacy-d1"


# ---------------------------------------------------------------------------
# Capacity / edge-case tests
# ---------------------------------------------------------------------------


class TestStoreCapacity:
    async def test_session_store_lru_eviction(self) -> None:
        from backend.store import SessionStore

        store = SessionStore(max_sessions=3)
        for i in range(4):
            await store.save(_make_result(f"s{i}"))
        # Oldest (s0) should be evicted
        assert store.get("s0") is None
        assert store.get("s1") is not None
        assert store.get("s3") is not None

    async def test_config_dump_store_fifo_eviction(self) -> None:
        from backend.store import ConfigDumpStore

        dstore = ConfigDumpStore(max_dumps=3)
        for i in range(4):
            await dstore.save(_make_dump(f"d{i}", "SW1"))
        assert dstore.get("d0") is None
        assert dstore.get("d3") is not None

    async def test_session_store_concurrent_saves(self) -> None:
        import asyncio

        from backend.store import SessionStore

        store = SessionStore(max_sessions=100)
        tasks = [store.save(_make_result(f"concurrent-{i}")) for i in range(20)]
        await asyncio.gather(*tasks)
        all_sessions = store.list_all()
        assert len(all_sessions) == 20
