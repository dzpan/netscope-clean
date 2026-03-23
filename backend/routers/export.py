"""Export and Backup router endpoints."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import Response

import backend.store as _store_module
from backend.config import settings
from backend.export import (
    export_csv_zip,
    export_dot,
    export_drawio,
    export_excel,
    export_json,
    export_svg,
)
from backend.models import SavedView, TopologyResult
from backend.routers._helpers import get_session_or_404
from backend.search import build_search_index
from backend.store import view_store

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.get("/export/{session_id}/drawio", tags=["Export"])
async def export_drawio_endpoint(session_id: str) -> Response:
    result = get_session_or_404(session_id)
    xml = export_drawio(result)
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="netscope_{session_id[:8]}.drawio"'},
    )


@router.get("/export/{session_id}/csv", tags=["Export"])
async def export_csv_endpoint(session_id: str) -> Response:
    result = get_session_or_404(session_id)
    data = export_csv_zip(result)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="netscope_{session_id[:8]}.zip"'},
    )


@router.get("/export/{session_id}/excel", tags=["Export"])
async def export_excel_endpoint(session_id: str) -> Response:
    result = get_session_or_404(session_id)
    data = export_excel(result)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="netscope_{session_id[:8]}.xlsx"'},
    )


@router.get("/export/{session_id}/dot", tags=["Export"])
async def export_dot_endpoint(session_id: str) -> Response:
    result = get_session_or_404(session_id)
    data = export_dot(result)
    return Response(
        content=data,
        media_type="text/vnd.graphviz",
        headers={"Content-Disposition": f'attachment; filename="netscope_{session_id[:8]}.dot"'},
    )


@router.get("/export/{session_id}/svg", tags=["Export"])
async def export_svg_endpoint(session_id: str) -> Response:
    result = get_session_or_404(session_id)
    try:
        data = export_svg(result)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="netscope_{session_id[:8]}.svg"'},
    )


@router.get("/export/{session_id}/json", tags=["Export"])
async def export_json_endpoint(session_id: str) -> Response:
    result = get_session_or_404(session_id)
    data = export_json(result)
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="netscope_{session_id[:8]}.json"'},
    )


# ---------------------------------------------------------------------------
# Backup / Restore & Session Import / Export
# ---------------------------------------------------------------------------


@router.get("/backup/database", tags=["Backup"])
async def backup_database() -> Response:
    """Download a copy of the SQLite database file."""
    if not settings.db_path:
        raise HTTPException(
            status_code=422,
            detail="Database backup requires NETSCOPE_DB_PATH to be set (SQLite mode)",
        )
    import shutil
    import tempfile

    db = Path(settings.db_path)
    if not db.exists():
        raise HTTPException(status_code=404, detail="Database file not found")

    # Copy to a temp file so we don't serve a file that's being written to
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        shutil.copy2(db, tmp_path)
        # Also copy WAL if it exists so backup is consistent
        wal = db.with_suffix(".db-wal")
        if wal.exists():
            shutil.copy2(wal, tmp_path.with_suffix(".db-wal"))
        data = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
        tmp_path.with_suffix(".db-wal").unlink(missing_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="netscope_backup_{ts}.db"'},
    )


@router.post("/backup/restore", tags=["Backup"])
async def restore_database(file: UploadFile) -> dict[str, str]:
    """Restore the SQLite database from an uploaded backup file.

    The server should be restarted after restore for stores to pick up new data.
    """
    if not settings.db_path:
        raise HTTPException(
            status_code=422,
            detail="Database restore requires NETSCOPE_DB_PATH to be set (SQLite mode)",
        )
    import shutil
    import sqlite3
    import tempfile

    content = await file.read()
    if len(content) < 100:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is too small to be a valid database",
        )

    # Validate it's a real SQLite database
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.write(content)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        conn = sqlite3.connect(str(tmp_path))
        # Check that required tables exist
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
        required = {"sessions"}
        missing = required - tables
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid NetScope backup: missing tables {missing}",
            )
    except sqlite3.DatabaseError as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Not a valid SQLite database: {exc}") from exc

    # Backup current DB before overwrite
    db = Path(settings.db_path)
    if db.exists():
        backup_path = db.with_suffix(f".db.bak.{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(db, backup_path)
        logger.info("Current database backed up to %s", backup_path)

    # Replace the database
    shutil.move(str(tmp_path), str(db))
    # Remove stale WAL/SHM files so SQLite doesn't get confused
    db.with_suffix(".db-wal").unlink(missing_ok=True)
    db.with_suffix(".db-shm").unlink(missing_ok=True)

    logger.info("Database restored from uploaded backup (%d bytes)", len(content))
    return {
        "status": "restored",
        "message": "Database restored. Restart the server to load the new data.",
        "size_bytes": str(len(content)),
    }


@router.get("/sessions/{session_id}/export-bundle", tags=["Sessions"])
async def export_session_bundle(session_id: str) -> Response:
    """Export a single session as a portable JSON bundle.

    Includes the topology result, saved views, and metadata.
    Does NOT include plaintext credentials.
    """
    result = get_session_or_404(session_id)

    # Gather related saved views
    views = view_store.list_all(session_id=session_id)

    bundle: dict[str, object] = {
        "format": "netscope-session-bundle",
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "session": json.loads(result.model_dump_json()),
        "saved_views": [json.loads(v.model_dump_json()) for v in views],
    }

    data = json.dumps(bundle, indent=2).encode()
    ts = result.discovered_at.strftime("%Y%m%d_%H%M%S")
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="netscope_session_{session_id[:8]}_{ts}.json"'
            )
        },
    )


@router.post("/sessions/import-bundle", tags=["Sessions"])
async def import_session_bundle(request: Request, file: UploadFile) -> dict[str, object]:
    """Import a session bundle (JSON) exported from another NetScope instance.

    Creates a new session (and saved views) from the bundle data.
    """
    content = await file.read()
    try:
        bundle = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    if bundle.get("format") != "netscope-session-bundle":
        raise HTTPException(
            status_code=400,
            detail="Not a valid NetScope session bundle (missing format marker)",
        )

    # Parse the session
    try:
        result = TopologyResult.model_validate(bundle["session"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid session data: {exc}") from exc

    # Save the session
    await _store_module.store.save(result)

    # Import saved views
    imported_views = 0
    for view_data in bundle.get("saved_views", []):
        try:
            view = SavedView.model_validate(view_data)
            await view_store.save(view)
            imported_views += 1
        except Exception:
            logger.warning("Skipped invalid saved view during import")

    # Rebuild search index if available
    _search_conn = request.app.state.search_conn
    if _search_conn is not None:
        build_search_index(_search_conn, result)

    logger.info(
        "Imported session %s (%d devices, %d views)",
        result.session_id,
        len(result.devices),
        imported_views,
    )
    return {
        "status": "imported",
        "session_id": result.session_id,
        "device_count": len(result.devices),
        "link_count": len(result.links),
        "imported_views": imported_views,
    }
