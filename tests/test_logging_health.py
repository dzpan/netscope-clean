"""Tests for structured logging, /health, and /logs endpoints."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.logging_config import JSONFormatter, LogBuffer
from backend.main import app

# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------


class TestJSONFormatter:
    def test_basic_format(self) -> None:
        import logging

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        raw = formatter.format(record)
        data = json.loads(raw)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert "timestamp" in data

    def test_extra_fields(self) -> None:
        import logging

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="device unreachable",
            args=(),
            exc_info=None,
        )
        record.device_ip = "10.0.0.1"  # type: ignore[attr-defined]
        record.session_id = "sess-123"  # type: ignore[attr-defined]
        raw = formatter.format(record)
        data = json.loads(raw)
        assert data["device_ip"] == "10.0.0.1"
        assert data["session_id"] == "sess-123"

    def test_exception_field(self) -> None:
        import logging

        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="failed",
                args=(),
                exc_info=sys.exc_info(),
            )
        raw = formatter.format(record)
        data = json.loads(raw)
        assert "exception" in data
        assert "ValueError: boom" in data["exception"]


# ---------------------------------------------------------------------------
# LogBuffer
# ---------------------------------------------------------------------------


class TestLogBuffer:
    def test_ring_buffer(self) -> None:
        buf = LogBuffer(capacity=3)
        formatter = JSONFormatter()
        buf.setFormatter(formatter)

        import logging

        for i in range(5):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="msg %d",
                args=(i,),
                exc_info=None,
            )
            buf.emit(record)

        lines = buf.get_lines()
        assert len(lines) == 3  # capacity is 3
        # Should have messages 2, 3, 4 (oldest evicted)
        assert "msg 2" in lines[0]
        assert "msg 4" in lines[2]

    def test_get_lines_with_limit(self) -> None:
        buf = LogBuffer(capacity=10)
        formatter = JSONFormatter()
        buf.setFormatter(formatter)

        import logging

        for i in range(5):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="msg %d",
                args=(i,),
                exc_info=None,
            )
            buf.emit(record)

        lines = buf.get_lines(limit=2)
        assert len(lines) == 2
        assert "msg 3" in lines[0]
        assert "msg 4" in lines[1]


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test/api/v1")


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "version" in data
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], (int, float))
    assert "started_at" in data
    assert "database" in data
    assert data["database_backend"] in ("sqlite", "memory")


# ---------------------------------------------------------------------------
# /logs endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logs_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/logs?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_logs_download(client: AsyncClient) -> None:
    resp = await client.get("/logs?limit=10&download=true")
    assert resp.status_code == 200
    assert "application/x-ndjson" in resp.headers["content-type"]
    assert "attachment" in resp.headers.get("content-disposition", "")
