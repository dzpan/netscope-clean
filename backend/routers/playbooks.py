"""Playbooks router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from backend.playbooks import (
    ConfigReplaceRequest,
    Playbook,
    PlaybookCreateRequest,
    PlaybookDryRunRequest,
    PlaybookExecuteRequest,
    PlaybookExecution,
    PlaybookUndoRequest,
    PlaybookUpdateRequest,
)

router = APIRouter()


def _require_advanced(request: Request) -> None:
    if request.app.state.audit_store is None:
        raise HTTPException(
            status_code=422,
            detail="Advanced Mode audit store failed to initialise",
        )


def _as_list(val: object) -> list[object]:
    """Safely coerce a value to a list for iteration."""
    return val if isinstance(val, list) else []


@router.get("/playbooks", response_model=list[Playbook], tags=["Playbooks"])
async def list_playbooks(
    request: Request,
    category: str | None = None,
    search: str | None = None,
) -> list[Playbook]:
    """List all playbooks with optional category/search filter."""
    _require_advanced(request)
    return request.app.state.playbook_store.list_playbooks(category=category, search=search)  # type: ignore[no-any-return]


@router.get("/playbooks/{playbook_id}", response_model=Playbook, tags=["Playbooks"])
async def get_playbook(request: Request, playbook_id: str) -> Playbook:
    """Get a single playbook by ID."""
    _require_advanced(request)
    pb = request.app.state.playbook_store.get_playbook(playbook_id)
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return pb  # type: ignore[no-any-return]


@router.post("/playbooks", response_model=Playbook, status_code=201, tags=["Playbooks"])
async def create_playbook(request: Request, req: PlaybookCreateRequest) -> Playbook:
    """Create a new playbook."""
    _require_advanced(request)
    now = datetime.now(UTC)
    pb = Playbook(
        title=req.title,
        description=req.description,
        category=req.category,
        platforms=req.platforms,
        variables=req.variables,
        pre_checks=req.pre_checks,
        steps=req.steps,
        post_checks=req.post_checks,
        rollback=req.rollback,
        builtin=False,
        created_at=now,
        updated_at=now,
    )
    await request.app.state.playbook_store.save_playbook(pb)
    return pb


@router.put("/playbooks/{playbook_id}", response_model=Playbook, tags=["Playbooks"])
async def update_playbook(
    request: Request, playbook_id: str, req: PlaybookUpdateRequest
) -> Playbook:
    """Update an existing playbook. Cannot modify builtins."""
    _require_advanced(request)
    _playbook_store = request.app.state.playbook_store
    existing = _playbook_store.get_playbook(playbook_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    if existing.builtin:
        raise HTTPException(status_code=403, detail="Cannot modify built-in playbooks")

    update_data: dict[str, object] = {}
    if req.title is not None:
        update_data["title"] = req.title
    if req.description is not None:
        update_data["description"] = req.description
    if req.category is not None:
        update_data["category"] = req.category
    if req.platforms is not None:
        update_data["platforms"] = req.platforms
    if req.variables is not None:
        update_data["variables"] = req.variables
    if req.pre_checks is not None:
        update_data["pre_checks"] = req.pre_checks
    if req.steps is not None:
        update_data["steps"] = req.steps
    if req.post_checks is not None:
        update_data["post_checks"] = req.post_checks
    if req.rollback is not None:
        update_data["rollback"] = req.rollback

    update_data["updated_at"] = datetime.now(UTC)
    updated = existing.model_copy(update=update_data)
    await _playbook_store.save_playbook(updated)
    return updated  # type: ignore[no-any-return]


@router.delete("/playbooks/{playbook_id}", status_code=204, tags=["Playbooks"])
async def delete_playbook(request: Request, playbook_id: str) -> None:
    """Delete a playbook. Cannot delete builtins."""
    _require_advanced(request)
    deleted = await request.app.state.playbook_store.delete_playbook(playbook_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Playbook not found or is a built-in template",
        )


@router.post("/playbooks/{playbook_id}/dry-run", tags=["Playbooks"])
async def playbook_dry_run(
    request: Request, playbook_id: str, req: PlaybookDryRunRequest
) -> dict[str, object]:
    """Preview interpolated commands without executing."""
    _require_advanced(request)
    pb = request.app.state.playbook_store.get_playbook(playbook_id)
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")

    from backend.playbook_engine import dry_run

    return await dry_run(
        pb,
        req.variables,
        device_ip=req.device_ip,
        device_platform=req.device_platform,
        username=req.username,
        password=req.password,
        enable_password=req.enable_password,
        timeout=req.timeout,
    )


@router.post(
    "/playbooks/{playbook_id}/execute",
    response_model=PlaybookExecution,
    status_code=201,
    tags=["Playbooks"],
)
async def execute_playbook_endpoint(
    request: Request,
    playbook_id: str,
    req: PlaybookExecuteRequest,
) -> PlaybookExecution:
    """Execute a playbook against one or more devices."""
    _require_advanced(request)
    _playbook_store = request.app.state.playbook_store
    pb = _playbook_store.get_playbook(playbook_id)
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")

    from backend.playbook_engine import execute_playbook

    execution = await execute_playbook(pb, req)
    await _playbook_store.save_execution(execution)
    return execution


@router.get("/playbook-runs", response_model=list[PlaybookExecution], tags=["Playbooks"])
async def list_playbook_runs(
    request: Request,
    playbook_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PlaybookExecution]:
    """List playbook execution history."""
    _require_advanced(request)
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    return request.app.state.playbook_store.list_executions(  # type: ignore[no-any-return]
        playbook_id=playbook_id, limit=limit, offset=offset
    )


@router.get("/playbook-runs/{run_id}", response_model=PlaybookExecution, tags=["Playbooks"])
async def get_playbook_run(request: Request, run_id: str) -> PlaybookExecution:
    """Get a single playbook execution by ID."""
    _require_advanced(request)
    execution = request.app.state.playbook_store.get_execution(run_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Playbook execution not found")
    return execution  # type: ignore[no-any-return]


@router.get("/playbook-runs/{run_id}/diff", tags=["Playbooks"])
async def diff_playbook_run(
    request: Request,
    run_id: str,
    compare_run_id: str | None = None,
) -> dict[str, object]:
    """Compare config snapshots within a playbook execution.

    Without ``compare_run_id``: returns per-device diff of pre-check vs
    post-check outputs (shows what the playbook changed).

    With ``compare_run_id``: returns per-device diff of post-check outputs
    between the two runs (shows config drift between executions).
    """
    import difflib

    _require_advanced(request)
    _playbook_store = request.app.state.playbook_store
    execution = _playbook_store.get_execution(run_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Playbook execution not found")

    compare: PlaybookExecution | None = None
    if compare_run_id:
        compare = _playbook_store.get_execution(compare_run_id)
        if compare is None:
            raise HTTPException(status_code=404, detail="Comparison execution not found")

    diffs: list[dict[str, object]] = []

    for dev in execution.device_results:
        device_diffs: dict[str, object] = {
            "device_id": dev.device_id,
            "device_ip": dev.device_ip,
            "commands": {},
        }

        if compare:
            compare_dev = next(
                (d for d in compare.device_results if d.device_id == dev.device_id),
                None,
            )
            cmd_diffs: dict[str, str] = {}
            for cmd, output_a in dev.post_check_outputs.items():
                output_b = compare_dev.post_check_outputs.get(cmd, "") if compare_dev else ""
                diff = "\n".join(
                    difflib.unified_diff(
                        output_a.splitlines(),
                        output_b.splitlines(),
                        fromfile=f"run:{run_id[:8]}",
                        tofile=f"run:{compare_run_id[:8] if compare_run_id else ''}",
                        lineterm="",
                    )
                )
                if diff:
                    cmd_diffs[cmd] = diff
            device_diffs["commands"] = cmd_diffs
        else:
            cmd_diffs = {}
            all_cmds = set(dev.pre_check_outputs.keys()) | set(dev.post_check_outputs.keys())
            for cmd in sorted(all_cmds):
                pre = dev.pre_check_outputs.get(cmd, "")
                post = dev.post_check_outputs.get(cmd, "")
                diff = "\n".join(
                    difflib.unified_diff(
                        pre.splitlines(),
                        post.splitlines(),
                        fromfile="before",
                        tofile="after",
                        lineterm="",
                    )
                )
                if diff:
                    cmd_diffs[cmd] = diff
            device_diffs["commands"] = cmd_diffs

        diffs.append(device_diffs)

    return {
        "run_id": run_id,
        "compare_run_id": compare_run_id,
        "playbook_title": execution.playbook_title,
        "device_diffs": diffs,
    }


@router.post(
    "/playbook-runs/{run_id}/undo",
    response_model=PlaybookExecution,
    status_code=201,
    tags=["Playbooks"],
)
async def undo_playbook_run(
    request: Request, run_id: str, req: PlaybookUndoRequest
) -> PlaybookExecution:
    """Undo a previous playbook execution by applying rollback commands."""
    _require_advanced(request)
    _playbook_store = request.app.state.playbook_store
    execution = _playbook_store.get_execution(run_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Playbook execution not found")

    from backend.playbook_engine import undo_execution

    undo_result = await undo_execution(
        execution,
        username=req.username,
        password=req.password,
        enable_password=req.enable_password,
        timeout=req.timeout,
    )
    await _playbook_store.save_execution(undo_result)
    return undo_result


@router.post("/playbooks/configure-replace", tags=["Playbooks"])
async def api_configure_replace(request: Request, req: ConfigReplaceRequest) -> dict[str, object]:
    """Execute IOS-XE configure replace to restore a saved config."""
    _require_advanced(request)
    from backend.playbook_engine import configure_replace

    result = await configure_replace(
        device_ip=req.device_ip,
        config_url=req.config_url,
        platform=req.device_platform,
        username=req.username,
        password=req.password,
        enable_password=req.enable_password,
        timeout=req.timeout,
    )
    return result


@router.post("/playbooks/import", response_model=Playbook, status_code=201, tags=["Playbooks"])
async def import_playbook(request: Request, body: dict[str, object]) -> Playbook:
    """Import a playbook from YAML-like dict structure."""
    _require_advanced(request)
    from backend.playbooks import Platform as Plat
    from backend.playbooks import PlaybookCategory as PBCat
    from backend.playbooks import PlaybookVariable as PBVar
    from backend.playbooks import VariableType as VT

    title = str(body.get("title", body.get("name", "Imported Playbook")))
    description = str(body.get("description", ""))

    try:
        category = PBCat(str(body.get("category", "general")))
    except ValueError:
        category = PBCat.GENERAL

    platforms_raw = body.get("platforms", body.get("platform", ["iosxe"]))
    platforms: list[Plat] = []
    if isinstance(platforms_raw, list):
        for p in platforms_raw:
            try:
                platforms.append(Plat(str(p)))
            except ValueError:
                pass
    if not platforms:
        platforms = [Plat.IOSXE]

    variables: list[PBVar] = []
    vars_raw = body.get("variables", [])
    for v in vars_raw if isinstance(vars_raw, list) else []:
        if isinstance(v, dict):
            vt_str = str(v.get("var_type", v.get("type", "string")))
            try:
                vt = VT(vt_str)
            except ValueError:
                vt = VT.STRING
            variables.append(
                PBVar(
                    name=str(v["name"]),
                    var_type=vt,
                    required=bool(v.get("required", True)),
                    default=str(v["default"]) if v.get("default") is not None else None,
                    description=str(v.get("description", "")),
                    choices=[str(c) for c in v.get("choices", [])],
                )
            )

    now = datetime.now(UTC)
    pb = Playbook(
        title=title,
        description=description,
        category=category,
        platforms=platforms,
        variables=variables,
        pre_checks=[str(c) for c in _as_list(body.get("pre_checks", []))],
        steps=[str(s) for s in _as_list(body.get("steps", []))],
        post_checks=[str(c) for c in _as_list(body.get("post_checks", []))],
        rollback=[str(r) for r in _as_list(body.get("rollback", []))],
        builtin=False,
        created_at=now,
        updated_at=now,
    )
    await request.app.state.playbook_store.save_playbook(pb)
    return pb


@router.get("/playbooks/{playbook_id}/export", tags=["Playbooks"])
async def export_playbook(request: Request, playbook_id: str) -> dict[str, object]:
    """Export a playbook as a YAML-compatible dict."""
    _require_advanced(request)
    pb = request.app.state.playbook_store.get_playbook(playbook_id)
    if pb is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return {
        "name": pb.title,
        "description": pb.description,
        "category": pb.category,
        "platform": [str(p) for p in pb.platforms],
        "variables": [
            {
                "name": v.name,
                "type": v.var_type,
                "required": v.required,
                **({"default": v.default} if v.default is not None else {}),
                "description": v.description or "",
                **({"choices": v.choices} if v.choices else {}),
            }
            for v in pb.variables
        ],
        "pre_checks": pb.pre_checks,
        "steps": pb.steps,
        "post_checks": pb.post_checks,
        "rollback": pb.rollback,
    }
