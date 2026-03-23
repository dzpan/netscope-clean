"""Advanced Mode router endpoints (VLAN changes, audit trail)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from backend.config import settings
from backend.models import (
    AuditExportFormat,
    AuditRecord,
    UndoRequest,
    VlanChangeRequest,
)
from backend.rate_limit import limiter

router = APIRouter()


def _require_advanced(request: Request) -> None:
    if request.app.state.audit_store is None:
        raise HTTPException(
            status_code=422,
            detail="Advanced Mode audit store failed to initialise",
        )


@router.get("/advanced/status", tags=["Advanced"])
async def advanced_status() -> dict[str, object]:
    """Return whether Advanced Mode is available and its configuration."""
    return {
        "allowed": True,
        "password_required": bool(settings.advanced_password),
        "require_write_mem": settings.advanced_require_write_mem,
        "max_ports_per_change": settings.advanced_max_ports_per_change,
        "audit_retention_days": settings.audit_retention_days,
    }


@router.post("/advanced/authenticate", tags=["Advanced"])
async def advanced_authenticate(body: dict[str, str]) -> dict[str, bool]:
    """Verify the Advanced Mode password."""
    import hmac

    password = body.get("password", "")
    if not settings.advanced_password:
        return {"authenticated": True}
    ok = hmac.compare_digest(password, settings.advanced_password)
    if not ok:
        raise HTTPException(status_code=403, detail="Invalid Advanced Mode password")
    return {"authenticated": True}


@router.post(
    "/advanced/vlan-change",
    response_model=AuditRecord,
    status_code=201,
    tags=["Advanced"],
)
@limiter.limit("10/minute")
async def vlan_change(request: Request, req: VlanChangeRequest) -> AuditRecord:
    """Execute a VLAN change on one or more access ports."""
    _require_advanced(request)
    _audit_store = request.app.state.audit_store
    if _audit_store is None:
        raise HTTPException(status_code=500, detail="Audit store not initialized")

    from backend.advanced import execute_vlan_change

    record = await execute_vlan_change(req)
    await _audit_store.create(record)
    return record


@router.get("/advanced/audit", response_model=list[AuditRecord], tags=["Advanced"])
async def list_audit(
    request: Request,
    device_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditRecord]:
    """List audit records (paginated, filterable by device)."""
    _require_advanced(request)
    _audit_store = request.app.state.audit_store
    if _audit_store is None:
        raise HTTPException(status_code=500, detail="Audit store not initialized")
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    return _audit_store.list_all(device_id=device_id, limit=limit, offset=offset)  # type: ignore[no-any-return]


@router.get("/advanced/audit/export", tags=["Advanced"])
async def export_audit(
    request: Request,
    fmt: AuditExportFormat = Query(default=AuditExportFormat.JSON, alias="format"),
    device_id: str | None = None,
) -> Response:
    """Export audit records as CSV or JSON."""
    _require_advanced(request)
    _audit_store = request.app.state.audit_store
    if _audit_store is None:
        raise HTTPException(status_code=500, detail="Audit store not initialized")
    if fmt == AuditExportFormat.CSV:
        data = _audit_store.export_csv(device_id=device_id)
        return Response(
            content=data,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
        )
    data = _audit_store.export_json(device_id=device_id)
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="audit.json"'},
    )


@router.get("/advanced/audit/{audit_id}", response_model=AuditRecord, tags=["Advanced"])
async def get_audit(request: Request, audit_id: str) -> AuditRecord:
    """Get a single audit record by ID."""
    _require_advanced(request)
    _audit_store = request.app.state.audit_store
    if _audit_store is None:
        raise HTTPException(status_code=500, detail="Audit store not initialized")
    record = _audit_store.get(audit_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return record  # type: ignore[no-any-return]


@router.post(
    "/advanced/audit/{audit_id}/undo",
    response_model=AuditRecord,
    status_code=201,
    tags=["Advanced"],
)
async def undo_audit(
    request: Request,
    audit_id: str,
    req: UndoRequest,
) -> AuditRecord:
    """Undo a previous VLAN change by applying its stored rollback commands."""
    _require_advanced(request)
    _audit_store = request.app.state.audit_store
    if _audit_store is None:
        raise HTTPException(status_code=500, detail="Audit store not initialized")

    original = _audit_store.get(audit_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Audit record not found")

    from backend.advanced import undo_change

    undo_record = await undo_change(
        original,
        username=req.username,
        password=req.password,
        enable_password=req.enable_password,
        timeout=req.timeout,
    )
    await _audit_store.create(undo_record)

    # Link the original record to its undo
    if undo_record.status == "success":
        await _audit_store.mark_rolled_back(audit_id, undo_record.id)

    return undo_record
