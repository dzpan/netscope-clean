"""Structured JSON logging for NetScope."""

from __future__ import annotations

import json
import logging
import sys
from collections import deque
from datetime import UTC, datetime
from threading import Lock
from typing import ClassVar


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        # Attach extra structured fields if present
        for key in ("device_ip", "session_id", "request_id"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class LogBuffer(logging.Handler):
    """Ring-buffer handler that retains the last N log records for export."""

    _instance: ClassVar[LogBuffer | None] = None
    _lock_cls: ClassVar[type] = Lock

    def __init__(self, capacity: int = 10_000) -> None:
        super().__init__()
        self._buffer: deque[str] = deque(maxlen=capacity)
        self._buf_lock = self._lock_cls()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._buf_lock:
                self._buffer.append(msg)
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def get_lines(self, limit: int = 0) -> list[str]:
        """Return buffered log lines (newest last). *limit=0* means all."""
        with self._buf_lock:
            if limit > 0:
                return list(self._buffer)[-limit:]
            return list(self._buffer)

    @classmethod
    def get_instance(cls) -> LogBuffer:
        if cls._instance is None:
            cls._instance = LogBuffer()
        return cls._instance


def setup_logging(level: str = "info") -> LogBuffer:
    """Configure the root logger with JSON output and an in-memory ring buffer.

    Returns the ``LogBuffer`` instance so callers can retrieve log lines.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Clear any existing handlers (e.g. basicConfig defaults)
    root.handlers.clear()

    formatter = JSONFormatter()

    # Console handler → stderr
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Ring-buffer handler (singleton)
    buf = LogBuffer.get_instance()
    buf.setFormatter(formatter)
    root.addHandler(buf)

    return buf
