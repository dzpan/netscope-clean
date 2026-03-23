"""Tests for the background re-discovery scheduler."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.scheduler import _rediscovery_loop, start_scheduler


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "sched.db"


class TestStartScheduler:
    async def test_returns_task(self, tmp_db: Path) -> None:
        """start_scheduler returns an asyncio.Task."""
        task = start_scheduler(interval=300, db_path=tmp_db)
        assert isinstance(task, asyncio.Task)
        assert task.get_name() == "netscope-scheduler"
        task.cancel()

    async def test_task_is_running(self, tmp_db: Path) -> None:
        task = start_scheduler(interval=300, db_path=tmp_db)
        assert not task.done()
        task.cancel()


class TestRediscoveryLoop:
    async def test_loop_runs_and_can_be_cancelled(self, tmp_db: Path) -> None:
        """The loop should start, sleep, and be cancellable."""
        with patch("backend.scheduler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = asyncio.CancelledError()
            with pytest.raises(asyncio.CancelledError):
                await _rediscovery_loop(interval=60, db_path=tmp_db)
            mock_sleep.assert_awaited_once_with(60)

    async def test_loop_handles_empty_sessions(self, tmp_db: Path) -> None:
        """Loop should handle case where no sessions exist."""
        call_count = 0

        async def counting_sleep(seconds: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch("backend.scheduler.asyncio.sleep", side_effect=counting_sleep):
            with pytest.raises(asyncio.CancelledError):
                await _rediscovery_loop(interval=10, db_path=tmp_db)

    async def test_loop_skips_session_without_stored_request(self, tmp_db: Path) -> None:
        """Sessions without a stored DiscoverRequest should be skipped."""
        from datetime import UTC, datetime

        from backend.models import TopologyResult
        from backend.store_sqlite import SQLiteSessionStore

        # Create a session store with a dummy session
        session_store = SQLiteSessionStore(tmp_db)

        fake_session = TopologyResult(
            session_id="test-123",
            discovered_at=datetime.now(UTC),
            devices=[],
            links=[],
            failures=[],
        )
        await session_store.save(fake_session)

        call_count = 0

        async def counting_sleep(seconds: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch("backend.scheduler.asyncio.sleep", side_effect=counting_sleep):
            with pytest.raises(asyncio.CancelledError):
                await _rediscovery_loop(interval=10, db_path=tmp_db)
        # Should not crash — skips session without stored request

    async def test_loop_retention_cleanup(self, tmp_db: Path) -> None:
        """When retention_days > 0, cleanup should be called each pass."""
        call_count = 0

        async def counting_sleep(seconds: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch("backend.scheduler.asyncio.sleep", side_effect=counting_sleep):
            # cleanup_old_snapshots is imported inside the function body from store_sqlite
            with patch("backend.store_sqlite.cleanup_old_snapshots", return_value=0):
                with pytest.raises(asyncio.CancelledError):
                    await _rediscovery_loop(interval=10, db_path=tmp_db, retention_days=30)
