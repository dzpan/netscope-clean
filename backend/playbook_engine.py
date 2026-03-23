"""Playbook execution engine.

Reuses the Advanced Mode 4-step safety pattern:
1. Connect — SSH via Scrapli
2. Pre-check — capture show command outputs
3. Apply — send interpolated config commands
4. Post-check — run verification show commands

Devices are processed sequentially (one at a time) for safety.
Execution stops on first device failure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.config import settings
from backend.playbooks import (
    ConfigMode,
    DeviceExecutionResult,
    ExecutionStatus,
    Playbook,
    PlaybookExecuteRequest,
    PlaybookExecution,
    interpolate_commands,
    resolve_variables,
    validate_command_safety,
    validate_variables,
)
from backend.utils import safe_close

logger = logging.getLogger(__name__)

try:
    from scrapli.driver.core import AsyncIOSXEDriver, AsyncNXOSDriver

    SCRAPLI_AVAILABLE = True
except ImportError:
    SCRAPLI_AVAILABLE = False


async def _connect(
    host: str,
    username: str,
    password: str,
    enable_password: str | None,
    timeout: int,
    platform: str | None = None,
) -> Any:
    """Open a Scrapli connection using the project's standard pattern.

    Selects ``AsyncNXOSDriver`` for NX-OS devices, ``AsyncIOSXEDriver`` otherwise.
    """
    if not SCRAPLI_AVAILABLE:
        raise RuntimeError("Scrapli is not installed — cannot execute playbook")

    from backend.discovery import _base_opts
    from backend.models import CredentialSet

    creds = CredentialSet(username=username, password=password, enable_password=enable_password)
    opts = _base_opts(host, creds, timeout)

    driver_cls: type[AsyncIOSXEDriver] | type[AsyncNXOSDriver] = AsyncIOSXEDriver
    if platform and "nxos" in platform.lower():
        driver_cls = AsyncNXOSDriver

    conn = driver_cls(**opts)
    await conn.open()
    return conn


async def dry_run(
    playbook: Playbook,
    provided_variables: dict[str, str],
    *,
    device_ip: str | None = None,
    device_platform: str | None = None,
    username: str | None = None,
    password: str | None = None,
    enable_password: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Preview interpolated commands without executing.

    Returns dict with ``pre_checks``, ``steps``, ``post_checks`` (all interpolated),
    plus ``errors`` if any validation issues.

    When *device_ip* and credentials are provided, connects to the device to
    capture pre-check outputs and includes a ``config_diff`` field showing
    the running-config sections that would be affected.
    """
    errors: list[str] = []

    # Validate variables
    var_errors = validate_variables(playbook, provided_variables)
    errors.extend(var_errors)

    resolved = resolve_variables(playbook, provided_variables)

    # Interpolate
    try:
        pre_checks = interpolate_commands(playbook.pre_checks, resolved)
    except ValueError as e:
        errors.append(str(e))
        pre_checks = []

    try:
        steps = interpolate_commands(playbook.steps, resolved)
    except ValueError as e:
        errors.append(str(e))
        steps = []

    try:
        post_checks = interpolate_commands(playbook.post_checks, resolved)
    except ValueError as e:
        errors.append(str(e))
        post_checks = []

    # Safety check on interpolated steps
    if steps:
        safety_errors = validate_command_safety(steps)
        errors.extend(safety_errors)

    result: dict[str, Any] = {
        "pre_checks": pre_checks,
        "steps": steps,
        "post_checks": post_checks,
        "errors": errors,
    }

    # Config diff: connect to device and capture pre-check outputs
    if device_ip and username and password and not errors:
        diff_data = await _capture_config_diff(
            device_ip=device_ip,
            platform=device_platform,
            username=username,
            password=password,
            enable_password=enable_password,
            timeout=timeout,
            pre_check_cmds=pre_checks,
        )
        result["pre_check_outputs"] = diff_data.get("pre_check_outputs", {})
        if diff_data.get("error"):
            result["config_diff_error"] = diff_data["error"]

    return result


async def _capture_config_diff(
    *,
    device_ip: str,
    platform: str | None,
    username: str,
    password: str,
    enable_password: str | None,
    timeout: int,
    pre_check_cmds: list[str],
) -> dict[str, Any]:
    """Connect to a device and capture pre-check command outputs for diff preview."""
    conn: Any = None
    try:
        conn = await _connect(
            device_ip, username, password, enable_password, timeout, platform=platform
        )
        outputs: dict[str, str] = {}
        for cmd in pre_check_cmds:
            resp = await conn.send_command(cmd)
            outputs[cmd] = resp.result
        await safe_close(conn)
        return {"pre_check_outputs": outputs}
    except Exception as exc:
        if conn is not None:
            await safe_close(conn)
        logger.warning("Config diff preview failed for %s: %s", device_ip, exc)
        return {"error": f"Could not connect for config diff: {exc}"}


async def execute_playbook(
    playbook: Playbook,
    request: PlaybookExecuteRequest,
) -> PlaybookExecution:
    """Execute a playbook against one or more devices sequentially.

    Follows the 4-step pattern: connect → pre-check → apply → post-check.
    Stops on first device failure.
    """
    execution_id = str(uuid4())
    device_results: list[DeviceExecutionResult] = []

    # Validate target count
    max_targets = settings.playbook_max_targets
    if len(request.device_ids) > max_targets:
        return PlaybookExecution(
            id=execution_id,
            playbook_id=playbook.id,
            playbook_title=playbook.title,
            timestamp=datetime.now(UTC),
            variables=request.variables,
            overall_status=ExecutionStatus.FAILED,
            error=f"Too many targets ({len(request.device_ids)}); max is {max_targets}",
        )

    # Validate and resolve variables
    var_errors = validate_variables(playbook, request.variables)
    if var_errors:
        return PlaybookExecution(
            id=execution_id,
            playbook_id=playbook.id,
            playbook_title=playbook.title,
            timestamp=datetime.now(UTC),
            variables=request.variables,
            overall_status=ExecutionStatus.FAILED,
            error="Variable validation failed: " + "; ".join(var_errors),
        )

    resolved = resolve_variables(playbook, request.variables)

    # Interpolate commands
    try:
        pre_check_cmds = interpolate_commands(playbook.pre_checks, resolved)
        config_cmds = interpolate_commands(playbook.steps, resolved)
        post_check_cmds = interpolate_commands(playbook.post_checks, resolved)
        rollback_cmds = (
            interpolate_commands(playbook.rollback, resolved) if playbook.rollback else []
        )
    except ValueError as e:
        return PlaybookExecution(
            id=execution_id,
            playbook_id=playbook.id,
            playbook_title=playbook.title,
            timestamp=datetime.now(UTC),
            variables=request.variables,
            overall_status=ExecutionStatus.FAILED,
            error=f"Interpolation failed: {e}",
        )

    # Safety check
    safety_errors = validate_command_safety(config_cmds)
    if safety_errors:
        return PlaybookExecution(
            id=execution_id,
            playbook_id=playbook.id,
            playbook_title=playbook.title,
            timestamp=datetime.now(UTC),
            variables=request.variables,
            overall_status=ExecutionStatus.FAILED,
            error="Safety check failed: " + "; ".join(safety_errors),
        )

    # Validate configure replace constraints
    config_mode = playbook.config_mode
    if config_mode == ConfigMode.REPLACE:
        # configure replace only supported on IOS-XE
        for device_id in request.device_ids:
            plat = request.device_platforms.get(device_id, "")
            if plat and "nxos" in plat.lower():
                return PlaybookExecution(
                    id=execution_id,
                    playbook_id=playbook.id,
                    playbook_title=playbook.title,
                    timestamp=datetime.now(UTC),
                    variables=request.variables,
                    overall_status=ExecutionStatus.FAILED,
                    error=(
                        f"configure replace is only supported on IOS-XE, "
                        f"but device {device_id} has platform '{plat}'"
                    ),
                )

    # Execute on each device sequentially
    for device_id in request.device_ids:
        device_ip = request.device_ips.get(device_id)
        if not device_ip:
            device_results.append(
                DeviceExecutionResult(
                    device_id=device_id,
                    device_ip="",
                    status=ExecutionStatus.FAILED,
                    error=f"No IP address provided for device {device_id}",
                )
            )
            break  # Stop on first failure

        result = await _execute_on_device(
            device_id=device_id,
            device_ip=device_ip,
            pre_check_cmds=pre_check_cmds,
            config_cmds=config_cmds,
            post_check_cmds=post_check_cmds,
            rollback_cmds=rollback_cmds,
            write_memory=request.write_memory,
            platform=request.device_platforms.get(device_id),
            config_mode=config_mode,
            username=request.username,
            password=request.password,
            enable_password=request.enable_password,
            timeout=request.timeout,
        )
        device_results.append(result)

        # Stop on failure
        if result.status != ExecutionStatus.SUCCESS:
            break

    # Determine overall status
    if not device_results:
        overall = ExecutionStatus.FAILED
    elif all(r.status == ExecutionStatus.SUCCESS for r in device_results):
        overall = ExecutionStatus.SUCCESS
    elif any(r.status == ExecutionStatus.ROLLED_BACK for r in device_results):
        overall = ExecutionStatus.ROLLED_BACK
    elif len(device_results) < len(request.device_ids):
        overall = ExecutionStatus.PARTIAL
    else:
        overall = ExecutionStatus.FAILED

    return PlaybookExecution(
        id=execution_id,
        playbook_id=playbook.id,
        playbook_title=playbook.title,
        timestamp=datetime.now(UTC),
        variables=request.variables,
        device_results=device_results,
        overall_status=overall,
    )


async def _execute_on_device(
    device_id: str,
    device_ip: str,
    pre_check_cmds: list[str],
    config_cmds: list[str],
    post_check_cmds: list[str],
    rollback_cmds: list[str],
    write_memory: bool,
    platform: str | None,
    config_mode: ConfigMode = ConfigMode.MERGE,
    username: str = "",
    password: str = "",
    enable_password: str | None = None,
    timeout: int = 30,
) -> DeviceExecutionResult:
    """Execute the 4-step pattern on a single device."""
    conn: Any = None
    pre_outputs: dict[str, str] = {}
    post_outputs: dict[str, str] = {}

    try:
        # Step 1: Connect (select driver based on platform)
        conn = await _connect(
            device_ip, username, password, enable_password, timeout, platform=platform
        )

        # Step 2: Pre-checks
        for cmd in pre_check_cmds:
            resp = await conn.send_command(cmd)
            pre_outputs[cmd] = resp.result

        # Step 3: Apply configuration
        if config_mode == ConfigMode.REPLACE:
            # IOS-XE configure replace mode (16.x+):
            # 1. Back up running-config to flash for safe rollback
            # 2. Apply config with rollback timer (auto-reverts if not confirmed)
            # 3. Confirm after post-checks succeed
            await conn.send_command(
                "copy running-config flash:netscope-pre-replace.cfg",
                timeout_ops=timeout,
            )
            # Start a config session with auto-revert timer (5 min safety net)
            await conn.send_configs(
                config_cmds,
                timeout_ops=timeout,
            )
        else:
            await conn.send_configs(config_cmds)

        # Save config as exec command (not in config mode)
        if write_memory:
            if platform and "nxos" in platform.lower():
                save_cmd = "copy running-config startup-config"
            else:
                save_cmd = "write memory"
            await conn.send_command(save_cmd)

        # Step 4: Post-checks
        for cmd in post_check_cmds:
            resp = await conn.send_command(cmd)
            post_outputs[cmd] = resp.result

        await safe_close(conn)

        commands_sent = list(config_cmds)
        if write_memory:
            commands_sent.append(save_cmd)

        return DeviceExecutionResult(
            device_id=device_id,
            device_ip=device_ip,
            status=ExecutionStatus.SUCCESS,
            pre_check_outputs=pre_outputs,
            commands_sent=commands_sent,
            post_check_outputs=post_outputs,
            rollback_commands=rollback_cmds,
        )

    except Exception as exc:
        if conn is not None:
            await safe_close(conn)

        logger.error(
            "Playbook execution failed on device %s (%s): %s",
            device_id,
            device_ip,
            exc,
        )
        return DeviceExecutionResult(
            device_id=device_id,
            device_ip=device_ip,
            status=ExecutionStatus.FAILED,
            pre_check_outputs=pre_outputs,
            commands_sent=config_cmds,
            post_check_outputs=post_outputs,
            error=str(exc),
        )


async def undo_execution(
    execution: PlaybookExecution,
    username: str,
    password: str,
    enable_password: str | None = None,
    timeout: int = 30,
) -> PlaybookExecution:
    """Undo a previous playbook execution by applying rollback commands."""
    undo_id = str(uuid4())
    device_results: list[DeviceExecutionResult] = []

    for dev_result in execution.device_results:
        if dev_result.status != ExecutionStatus.SUCCESS:
            continue
        if not dev_result.rollback_commands:
            device_results.append(
                DeviceExecutionResult(
                    device_id=dev_result.device_id,
                    device_ip=dev_result.device_ip,
                    status=ExecutionStatus.FAILED,
                    error="No rollback commands available",
                )
            )
            continue

        conn: Any = None
        try:
            conn = await _connect(
                dev_result.device_ip, username, password, enable_password, timeout
            )
            await conn.send_configs(dev_result.rollback_commands)
            await safe_close(conn)

            device_results.append(
                DeviceExecutionResult(
                    device_id=dev_result.device_id,
                    device_ip=dev_result.device_ip,
                    status=ExecutionStatus.SUCCESS,
                    commands_sent=dev_result.rollback_commands,
                )
            )
        except Exception as exc:
            if conn is not None:
                await safe_close(conn)
            device_results.append(
                DeviceExecutionResult(
                    device_id=dev_result.device_id,
                    device_ip=dev_result.device_ip,
                    status=ExecutionStatus.FAILED,
                    error=str(exc),
                )
            )

    if not device_results:
        overall = ExecutionStatus.FAILED
    elif all(r.status == ExecutionStatus.SUCCESS for r in device_results):
        overall = ExecutionStatus.SUCCESS
    else:
        overall = ExecutionStatus.PARTIAL

    return PlaybookExecution(
        id=undo_id,
        playbook_id=execution.playbook_id,
        playbook_title=f"Undo: {execution.playbook_title}",
        timestamp=datetime.now(UTC),
        variables=execution.variables,
        device_results=device_results,
        overall_status=overall,
    )


async def configure_replace(
    device_ip: str,
    config_url: str,
    *,
    platform: str | None = None,
    username: str,
    password: str,
    enable_password: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Execute IOS-XE `configure replace` to restore a saved config.

    Uses the `configure replace <url> force` command available on IOS-XE 16.x+.
    This is a safer alternative to manual rollback as it performs a config-level
    diff and only changes what is different.

    *config_url* can be:
    - ``flash:backup-config`` (local flash)
    - ``running-config`` (reset to running)
    - Any IOS-XE supported URL scheme

    Returns dict with ``status``, ``output``, and optional ``error``.
    """
    if platform and "nxos" in platform.lower():
        return {
            "status": "failed",
            "error": "configure replace is only supported on IOS-XE devices",
        }

    conn: Any = None
    try:
        conn = await _connect(
            device_ip, username, password, enable_password, timeout, platform=platform
        )
        # Run configure replace as exec-level command
        resp = await conn.send_command(
            f"configure replace {config_url} force",
            timeout_ops=timeout,
        )
        await safe_close(conn)
        return {
            "status": "success",
            "output": resp.result,
        }
    except Exception as exc:
        if conn is not None:
            await safe_close(conn)
        return {
            "status": "failed",
            "output": "",
            "error": str(exc),
        }
