"""Health and Settings router endpoints."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.responses import JSONResponse as StarletteJSONResponse

import backend.store as _store_module
from backend.config import settings
from backend.discovery import probe_device

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health(request: Request) -> dict[str, object]:
    uptime_seconds = round(time.monotonic() - request.app.state.start_time, 1)
    db_ok = True
    if settings.db_path:
        try:
            from backend.store_sqlite import _open_db as _health_open_db

            conn = _health_open_db(Path(settings.db_path))
            conn.execute("SELECT 1")
            conn.close()
        except Exception:  # noqa: BLE001
            db_ok = False

    last_discovery: str | None = None
    sessions = _store_module.store.list_all()
    if sessions:
        latest = max(sessions, key=lambda s: s.discovered_at)
        last_discovery = latest.discovered_at.isoformat()

    return {
        "status": "ok" if db_ok else "degraded",
        "version": request.app.version,
        "uptime_seconds": uptime_seconds,
        "started_at": request.app.state.start_timestamp.isoformat(),
        "database": "connected" if db_ok else "error",
        "database_backend": "sqlite" if settings.db_path else "memory",
        "last_discovery": last_discovery,
    }


@router.get("/logs", tags=["Health"])
async def get_logs(
    request: Request,
    limit: int = Query(default=500, ge=1, le=10_000),
    download: bool = Query(default=False),
) -> Response:
    """Return recent log lines as JSON array, or as a downloadable file."""
    lines = request.app.state.log_buffer.get_lines(limit)
    if download:
        content = "\n".join(lines) + "\n"
        return Response(
            content=content,
            media_type="application/x-ndjson",
            headers={"Content-Disposition": "attachment; filename=netscope-logs.jsonl"},
        )
    # Return parsed JSON objects
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            parsed.append({"raw": line})
    return StarletteJSONResponse(content=parsed)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings", tags=["Settings"])
async def get_settings_endpoint(request: Request) -> dict[str, object]:
    """Return all settings (merged: saved values + env overrides)."""
    return request.app.state.settings_store.get()  # type: ignore[no-any-return]


@router.put("/settings", tags=["Settings"])
async def update_settings_endpoint(
    request: Request, payload: dict[str, object]
) -> dict[str, object]:
    """Update user-configurable settings. Env vars still override."""
    return request.app.state.settings_store.update(payload)  # type: ignore[no-any-return]


@router.post("/settings/test-credential", tags=["Settings"])
async def test_credential_endpoint(payload: dict[str, object]) -> dict[str, object]:
    """Test SSH connectivity with a credential set."""
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    enable_password = payload.get("enable_password")
    host = str(payload.get("host", ""))
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if not host:
        # No host specified — just validate the credential format is ok
        return {"success": True, "message": "Credentials accepted (no host to test)"}
    try:
        success, info = await probe_device(
            host=host,
            username=username,
            password=password,
            enable_password=str(enable_password) if enable_password is not None else None,
            timeout=15,
        )
        return {
            "success": success,
            "hostname": info.get("hostname"),
            "platform": info.get("platform"),
            "error": info.get("error"),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.post("/settings/reset", tags=["Settings"])
async def reset_settings_endpoint(request: Request) -> dict[str, object]:
    """Reset all settings to defaults."""
    return request.app.state.settings_store.reset()  # type: ignore[no-any-return]
