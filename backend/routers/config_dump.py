"""Config Dump router endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.config_dump import run_config_dump
from backend.models import ConfigDump, ConfigDumpRequest
from backend.store import dump_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/config-dump", response_model=ConfigDump, tags=["Config Dump"])
async def create_config_dump(req: ConfigDumpRequest) -> ConfigDump:
    """SSH into a device, run all show commands, store and return the dump."""
    try:
        dump = await run_config_dump(req)
    except Exception as exc:
        logger.exception("Config dump failed for %s", req.device_ip)
        detail = "Connection failed"
        msg = str(exc).lower()
        if "auth" in msg or "permission" in msg:
            detail = "Authentication failed"
        elif "timeout" in msg or "timed out" in msg:
            detail = "Connection timed out"
        elif "refused" in msg or "unreachable" in msg:
            detail = "Device unreachable"
        raise HTTPException(status_code=502, detail=detail)
    await dump_store.save(dump)
    return dump


@router.get("/config-dump", response_model=list[ConfigDump], tags=["Config Dump"])
async def list_config_dumps(device_id: str | None = None) -> list[ConfigDump]:
    if device_id:
        return dump_store.list_for_device(device_id)
    return dump_store.list_all()


@router.get("/config-dump/{dump_id}", response_model=ConfigDump, tags=["Config Dump"])
async def get_config_dump(dump_id: str) -> ConfigDump:
    dump = dump_store.get(dump_id)
    if not dump:
        raise HTTPException(status_code=404, detail="Config dump not found")
    return dump


@router.get("/config-dump/{dump_id}/download", tags=["Config Dump"])
async def download_config_dump(dump_id: str) -> Response:
    dump = dump_store.get(dump_id)
    if not dump:
        raise HTTPException(status_code=404, detail="Config dump not found")

    lines: list[str] = [
        "NetScope Config Dump",
        f"Device:  {dump.device_id}  ({dump.device_ip})",
        f"Date:    {dump.dumped_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Dump ID: {dump.dump_id}",
        "=" * 72,
        "",
    ]
    for cr in dump.commands:
        lines.append(f"{'=' * 72}")
        lines.append(f"### {cr.command}")
        lines.append(f"{'=' * 72}")
        if cr.error:
            lines.append(f"ERROR: {cr.error}")
        else:
            lines.append(cr.output)
        lines.append("")

    content = "\n".join(lines)
    filename = f"{dump.device_id}_{dump.dumped_at.strftime('%Y%m%d_%H%M%S')}.txt"
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
