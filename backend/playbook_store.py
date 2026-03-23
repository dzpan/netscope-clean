"""Playbook and execution persistence.

Supports two backends:
- In-memory (default, no persistence)
- SQLite (when NETSCOPE_DB_PATH is set)

Follows the same dual-store pattern as ``audit_store.py``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.playbooks import Playbook, PlaybookExecution


class PlaybookStore:
    """In-memory playbook store."""

    def __init__(self) -> None:
        self._playbooks: dict[str, Playbook] = {}
        self._executions: list[PlaybookExecution] = []
        self._lock = asyncio.Lock()

    async def save_playbook(self, playbook: Playbook) -> None:
        async with self._lock:
            self._playbooks[playbook.id] = playbook

    def get_playbook(self, playbook_id: str) -> Playbook | None:
        return self._playbooks.get(playbook_id)

    def list_playbooks(
        self,
        category: str | None = None,
        search: str | None = None,
    ) -> list[Playbook]:
        result = list(self._playbooks.values())
        if category:
            result = [p for p in result if p.category == category]
        if search:
            q = search.lower()
            result = [p for p in result if q in p.title.lower() or q in p.description.lower()]
        return sorted(result, key=lambda p: p.title)

    async def delete_playbook(self, playbook_id: str) -> bool:
        async with self._lock:
            if playbook_id in self._playbooks:
                # Don't allow deleting builtins
                if self._playbooks[playbook_id].builtin:
                    return False
                del self._playbooks[playbook_id]
                return True
            return False

    async def save_execution(self, execution: PlaybookExecution) -> None:
        async with self._lock:
            self._executions.append(execution)

    def get_execution(self, execution_id: str) -> PlaybookExecution | None:
        for e in self._executions:
            if e.id == execution_id:
                return e
        return None

    def list_executions(
        self,
        playbook_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PlaybookExecution]:
        filtered = self._executions
        if playbook_id:
            filtered = [e for e in filtered if e.playbook_id == playbook_id]
        filtered = sorted(filtered, key=lambda e: e.timestamp, reverse=True)
        return filtered[offset : offset + limit]

    async def cleanup_executions(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with self._lock:
            before = len(self._executions)
            self._executions = [e for e in self._executions if e.timestamp > cutoff]
            return before - len(self._executions)


class SQLitePlaybookStore:
    """SQLite-backed playbook store."""

    def __init__(self, db_path: Path) -> None:
        from backend.store_sqlite import _open_db

        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()

    async def save_playbook(self, playbook: Playbook) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO playbooks"
                " (id, title, category, builtin, created_at, updated_at, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    playbook.id,
                    playbook.title,
                    playbook.category,
                    1 if playbook.builtin else 0,
                    playbook.created_at.isoformat() if playbook.created_at else "",
                    playbook.updated_at.isoformat() if playbook.updated_at else None,
                    playbook.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get_playbook(self, playbook_id: str) -> Playbook | None:
        row = self._conn.execute(
            "SELECT data FROM playbooks WHERE id = ?", (playbook_id,)
        ).fetchone()
        if row is None:
            return None
        return Playbook.model_validate_json(row[0])

    def list_playbooks(
        self,
        category: str | None = None,
        search: str | None = None,
    ) -> list[Playbook]:
        if category and search:
            rows = self._conn.execute(
                "SELECT data FROM playbooks WHERE category = ?"
                " AND (title LIKE ? OR data LIKE ?) ORDER BY title",
                (category, f"%{search}%", f"%{search}%"),
            ).fetchall()
        elif category:
            rows = self._conn.execute(
                "SELECT data FROM playbooks WHERE category = ? ORDER BY title",
                (category,),
            ).fetchall()
        elif search:
            rows = self._conn.execute(
                "SELECT data FROM playbooks WHERE title LIKE ? OR data LIKE ? ORDER BY title",
                (f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT data FROM playbooks ORDER BY title").fetchall()
        return [Playbook.model_validate_json(r[0]) for r in rows]

    async def delete_playbook(self, playbook_id: str) -> bool:
        async with self._lock:
            # Check if builtin
            row = self._conn.execute(
                "SELECT builtin FROM playbooks WHERE id = ?", (playbook_id,)
            ).fetchone()
            if row is None:
                return False
            if row[0]:
                return False
            self._conn.execute("DELETE FROM playbooks WHERE id = ?", (playbook_id,))
            self._conn.commit()
            return True

    async def save_execution(self, execution: PlaybookExecution) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT INTO playbook_executions"
                " (id, playbook_id, timestamp, overall_status, data)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    execution.id,
                    execution.playbook_id,
                    execution.timestamp.isoformat(),
                    execution.overall_status,
                    execution.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get_execution(self, execution_id: str) -> PlaybookExecution | None:
        row = self._conn.execute(
            "SELECT data FROM playbook_executions WHERE id = ?", (execution_id,)
        ).fetchone()
        if row is None:
            return None
        return PlaybookExecution.model_validate_json(row[0])

    def list_executions(
        self,
        playbook_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PlaybookExecution]:
        if playbook_id:
            rows = self._conn.execute(
                "SELECT data FROM playbook_executions WHERE playbook_id = ?"
                " ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (playbook_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data FROM playbook_executions ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [PlaybookExecution.model_validate_json(r[0]) for r in rows]

    async def cleanup_executions(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        async with self._lock:
            cur = self._conn.execute(
                "DELETE FROM playbook_executions WHERE timestamp < ?", (cutoff,)
            )
            self._conn.commit()
            return cur.rowcount


def make_playbook_store() -> PlaybookStore | SQLitePlaybookStore:
    """Factory: returns SQLitePlaybookStore when DB_PATH is set, else in-memory."""
    from backend.config import settings

    if settings.db_path:
        return SQLitePlaybookStore(Path(settings.db_path))
    return PlaybookStore()
