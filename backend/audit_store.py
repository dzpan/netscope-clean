"""Audit record persistence for Advanced Mode operations.

Supports two backends:
- In-memory list (default, no persistence)
- SQLite table (when NETSCOPE_DB_PATH is set)

Records are immutable — never updated, only appended.
Undo relationships are tracked via ``undo_of`` / ``undone_by`` fields.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.models import AuditRecord


class AuditStore:
    """In-memory audit record store."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = asyncio.Lock()

    async def create(self, record: AuditRecord) -> None:
        async with self._lock:
            self._records.append(record)

    def get(self, audit_id: str) -> AuditRecord | None:
        for r in self._records:
            if r.id == audit_id:
                return r
        return None

    def list_all(
        self,
        device_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditRecord]:
        filtered = self._records
        if device_id:
            filtered = [r for r in filtered if r.device_id == device_id]
        # Newest first
        filtered = sorted(filtered, key=lambda r: r.timestamp, reverse=True)
        return filtered[offset : offset + limit]

    async def mark_rolled_back(self, audit_id: str, undone_by_id: str) -> bool:
        """Set ``undone_by`` on an existing record. Returns True if found."""
        async with self._lock:
            for i, r in enumerate(self._records):
                if r.id == audit_id:
                    self._records[i] = r.model_copy(update={"undone_by": undone_by_id})
                    return True
        return False

    def check_conflicts(self, device_id: str, interfaces: list[str]) -> list[AuditRecord]:
        """Return in-progress records that overlap the same device+interfaces."""
        # For now, check if any recent record (last 5 min) is still pending
        cutoff = datetime.now(UTC) - timedelta(minutes=5)
        conflicts: list[AuditRecord] = []
        intf_set = set(interfaces)
        for r in self._records:
            if (
                r.device_id == device_id
                and r.timestamp > cutoff
                and r.status == "success"
                and r.undone_by is None
                and any(c.interface in intf_set for c in r.changes)
            ):
                conflicts.append(r)
        return conflicts

    def export_csv(self, device_id: str | None = None) -> str:
        records = self.list_all(device_id=device_id, limit=10000)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "timestamp",
                "device_id",
                "device_ip",
                "platform",
                "operation",
                "status",
                "changes",
                "error",
                "undo_of",
                "undone_by",
            ]
        )
        for r in records:
            changes_str = "; ".join(
                f"{c.interface}: {c.old_value}->{c.new_value}" for c in r.changes
            )
            writer.writerow(
                [
                    r.id,
                    r.timestamp.isoformat(),
                    r.device_id,
                    r.device_ip,
                    r.platform or "",
                    r.operation,
                    r.status,
                    changes_str,
                    r.error or "",
                    r.undo_of or "",
                    r.undone_by or "",
                ]
            )
        return buf.getvalue()

    def export_json(self, device_id: str | None = None) -> str:
        records = self.list_all(device_id=device_id, limit=10000)
        return json.dumps([r.model_dump(mode="json") for r in records], indent=2)

    async def cleanup(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if r.timestamp > cutoff]
            return before - len(self._records)


class SQLiteAuditStore:
    """SQLite-backed audit store for persistent audit trail."""

    def __init__(self, db_path: Path) -> None:
        from backend.store_sqlite import _open_db

        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()

    async def create(self, record: AuditRecord) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT INTO audit_records"
                " (id, timestamp, device_id, device_ip, operation, status,"
                "  undo_of, undone_by, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.timestamp.isoformat(),
                    record.device_id,
                    record.device_ip,
                    record.operation,
                    record.status,
                    record.undo_of,
                    record.undone_by,
                    record.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get(self, audit_id: str) -> AuditRecord | None:
        row = self._conn.execute(
            "SELECT data FROM audit_records WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return AuditRecord.model_validate_json(row[0])

    def list_all(
        self,
        device_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditRecord]:
        if device_id:
            rows = self._conn.execute(
                "SELECT data FROM audit_records WHERE device_id = ?"
                " ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (device_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT data FROM audit_records ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [AuditRecord.model_validate_json(r[0]) for r in rows]

    async def mark_rolled_back(self, audit_id: str, undone_by_id: str) -> bool:
        async with self._lock:
            record = self.get(audit_id)
            if record is None:
                return False
            updated = record.model_copy(update={"undone_by": undone_by_id})
            self._conn.execute(
                "UPDATE audit_records SET undone_by = ?, data = ? WHERE id = ?",
                (undone_by_id, updated.model_dump_json(), audit_id),
            )
            self._conn.commit()
            return True

    def check_conflicts(self, device_id: str, interfaces: list[str]) -> list[AuditRecord]:
        cutoff = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        rows = self._conn.execute(
            "SELECT data FROM audit_records"
            " WHERE device_id = ? AND timestamp > ? AND status = 'success'"
            " AND undone_by IS NULL"
            " ORDER BY timestamp DESC",
            (device_id, cutoff),
        ).fetchall()
        intf_set = set(interfaces)
        conflicts: list[AuditRecord] = []
        for row in rows:
            record = AuditRecord.model_validate_json(row[0])
            if any(c.interface in intf_set for c in record.changes):
                conflicts.append(record)
        return conflicts

    def export_csv(self, device_id: str | None = None) -> str:
        records = self.list_all(device_id=device_id, limit=10000)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "timestamp",
                "device_id",
                "device_ip",
                "platform",
                "operation",
                "status",
                "changes",
                "error",
                "undo_of",
                "undone_by",
            ]
        )
        for r in records:
            changes_str = "; ".join(
                f"{c.interface}: {c.old_value}->{c.new_value}" for c in r.changes
            )
            writer.writerow(
                [
                    r.id,
                    r.timestamp.isoformat(),
                    r.device_id,
                    r.device_ip,
                    r.platform or "",
                    r.operation,
                    r.status,
                    changes_str,
                    r.error or "",
                    r.undo_of or "",
                    r.undone_by or "",
                ]
            )
        return buf.getvalue()

    def export_json(self, device_id: str | None = None) -> str:
        records = self.list_all(device_id=device_id, limit=10000)
        return json.dumps([r.model_dump(mode="json") for r in records], indent=2)

    async def cleanup(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        async with self._lock:
            cur = self._conn.execute("DELETE FROM audit_records WHERE timestamp < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount


def make_audit_store() -> AuditStore | SQLiteAuditStore:
    """Factory: returns SQLiteAuditStore when DB_PATH is set, else in-memory."""
    from backend.config import settings

    if settings.db_path:
        return SQLiteAuditStore(Path(settings.db_path))
    return AuditStore()
