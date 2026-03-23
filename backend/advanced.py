"""Advanced Mode — VLAN change execution engine.

Implements the 4-step process:
1. Connect — SSH via Scrapli using stored credentials
2. Pre-check — ``show running-config interface <intf>`` for rollback snapshot
3. Apply — ``send_configs()`` with VLAN change commands
4. Post-check — ``show interfaces status`` to verify. Auto-rollback on failure.

Safety guardrails enforced before any change:
- No trunk port changes
- No management interface changes (Vlan*, Loopback*, mgmt*)
- No port-channel member changes
- VLAN must exist on device
- Max N ports per change (configurable)
- One concurrent change per device (asyncio.Lock per device)
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.config import settings
from backend.models import (
    AdvancedStatus,
    AuditRecord,
    PortChange,
    VlanChangeRequest,
)
from backend.utils import safe_close

logger = logging.getLogger(__name__)

try:
    from scrapli.driver.core import AsyncIOSXEDriver

    SCRAPLI_AVAILABLE = True
except ImportError:
    SCRAPLI_AVAILABLE = False

# Per-device concurrency locks
_device_locks: dict[str, asyncio.Lock] = {}

# Interfaces that must never be modified
_PROTECTED_INTF_PATTERNS = re.compile(
    r"^(vlan|loopback|lo|mgmt|management|nve|tunnel|port-channel|po)\d*$",
    re.IGNORECASE,
)

# Trunk mode indicators in running-config
_TRUNK_INDICATORS = re.compile(r"switchport\s+mode\s+trunk", re.IGNORECASE)

# Port-channel membership indicator
_CHANNEL_GROUP_RE = re.compile(r"channel-group\s+\d+", re.IGNORECASE)


def _get_device_lock(device_id: str) -> asyncio.Lock:
    if device_id not in _device_locks:
        _device_locks[device_id] = asyncio.Lock()
    return _device_locks[device_id]


def generate_vlan_commands(
    interfaces: list[str],
    target_vlan: int,
    description: str | None = None,
    write_mem: bool = False,
    platform: str | None = None,
) -> list[str]:
    """Generate IOS/NX-OS commands to change VLAN on access ports."""
    commands: list[str] = []
    for intf in interfaces:
        commands.append(f"interface {intf}")
        commands.append(f"switchport access vlan {target_vlan}")
        if description is not None:
            commands.append(f"description {description}")
    if write_mem:
        if platform and "nxos" in platform.lower():
            commands.append("copy running-config startup-config")
        else:
            commands.append("write memory")
    return commands


def generate_rollback_commands(
    pre_state: dict[str, str],
    write_mem: bool = False,
    platform: str | None = None,
) -> list[str]:
    """Generate commands to restore interfaces to their pre-change state."""
    commands: list[str] = []
    for intf, config_snippet in pre_state.items():
        commands.append(f"interface {intf}")
        # Extract VLAN from pre-state
        vlan_match = re.search(r"switchport access vlan (\d+)", config_snippet)
        if vlan_match:
            commands.append(f"switchport access vlan {vlan_match.group(1)}")
        else:
            commands.append("no switchport access vlan")
        # Extract description
        desc_match = re.search(r"description (.+)", config_snippet)
        if desc_match:
            commands.append(f"description {desc_match.group(1).strip()}")
        else:
            commands.append("no description")
    if write_mem:
        if platform and "nxos" in platform.lower():
            commands.append("copy running-config startup-config")
        else:
            commands.append("write memory")
    return commands


def _validate_interface(intf: str) -> str | None:
    """Return error message if interface is protected, or None if safe."""
    if _PROTECTED_INTF_PATTERNS.match(intf):
        return f"Interface {intf} is a protected interface type"
    return None


def _check_trunk_or_channel(config: str, intf: str) -> str | None:
    """Return error if config indicates trunk mode or port-channel membership."""
    if _TRUNK_INDICATORS.search(config):
        return f"Interface {intf} is in trunk mode — trunk changes not allowed"
    if _CHANNEL_GROUP_RE.search(config):
        return f"Interface {intf} is a port-channel member — cannot modify directly"
    return None


def _extract_current_vlan(config: str) -> str | None:
    """Extract current access VLAN from running-config snippet."""
    m = re.search(r"switchport access vlan (\d+)", config)
    return m.group(1) if m else None


def _parse_intf_status_line(output: str, intf: str) -> str | None:
    """Extract VLAN from ``show interfaces status`` output for a specific interface."""
    for line in output.splitlines():
        # Normalize interface name for matching
        parts = line.split()
        if len(parts) >= 4 and _intf_matches(parts[0], intf):
            # VLAN is typically the 3rd column (after Port and Name)
            # But column positions vary; look for numeric VLAN value
            for part in parts[2:5]:
                if part.isdigit():
                    return part
    return None


def _intf_matches(short: str, full: str) -> bool:
    """Check if a short interface name matches a full one."""
    # Normalize both
    short_norm = short.lower().replace(" ", "")
    full_norm = full.lower().replace(" ", "")
    if short_norm == full_norm:
        return True
    # Try abbreviation expansion
    abbrevs = {
        "gi": "gigabitethernet",
        "fa": "fastethernet",
        "te": "tengigabitethernet",
        "eth": "ethernet",
        "hu": "hundredgige",
        "twe": "twentyfivegige",
        "fo": "fortygigabitethernet",
    }
    for abbr, exp in abbrevs.items():
        if short_norm.startswith(abbr) and full_norm.startswith(exp):
            if short_norm[len(abbr) :] == full_norm[len(exp) :]:
                return True
        if full_norm.startswith(abbr) and short_norm.startswith(exp):
            if full_norm[len(abbr) :] == short_norm[len(exp) :]:
                return True
    return False


async def _connect(
    host: str,
    username: str,
    password: str,
    enable_password: str | None,
    timeout: int,
) -> Any:
    """Open a Scrapli connection using the project's standard pattern."""
    if not SCRAPLI_AVAILABLE:
        raise RuntimeError("Scrapli is not installed — cannot execute changes")

    from backend.discovery import _base_opts
    from backend.models import CredentialSet

    creds = CredentialSet(
        username=username,
        password=password,
        enable_password=enable_password,
    )
    opts = _base_opts(host, creds, timeout)
    conn = AsyncIOSXEDriver(**opts)
    await conn.open()
    return conn


async def execute_vlan_change(request: VlanChangeRequest) -> AuditRecord:
    """Execute a VLAN change with full pre/post checks and audit trail."""
    # Validate interface count
    max_ports = settings.advanced_max_ports_per_change
    if len(request.interfaces) > max_ports:
        return AuditRecord(
            id=str(uuid4()),
            timestamp=datetime.now(UTC),
            device_id=request.device_id,
            device_ip=request.device_ip,
            platform=request.platform,
            operation="vlan_change",
            status=AdvancedStatus.FAILED,
            error=f"Too many ports ({len(request.interfaces)}); max is {max_ports}",
        )

    # Validate interface names
    for intf in request.interfaces:
        err = _validate_interface(intf)
        if err:
            return AuditRecord(
                id=str(uuid4()),
                timestamp=datetime.now(UTC),
                device_id=request.device_id,
                device_ip=request.device_ip,
                platform=request.platform,
                operation="vlan_change",
                status=AdvancedStatus.FAILED,
                error=err,
            )

    lock = _get_device_lock(request.device_id)
    if lock.locked():
        return AuditRecord(
            id=str(uuid4()),
            timestamp=datetime.now(UTC),
            device_id=request.device_id,
            device_ip=request.device_ip,
            platform=request.platform,
            operation="vlan_change",
            status=AdvancedStatus.FAILED,
            error=f"Another change is in progress on device {request.device_id}",
        )

    async with lock:
        return await _execute_vlan_change_locked(request)


async def _execute_vlan_change_locked(request: VlanChangeRequest) -> AuditRecord:
    """Inner implementation — must be called while holding the device lock."""
    audit_id = str(uuid4())
    pre_state: dict[str, str] = {}
    commands_sent: list[str] = []
    changes: list[PortChange] = []

    conn: Any = None
    try:
        # Step 1: Connect
        conn = await _connect(
            request.device_ip,
            request.username,
            request.password,
            request.enable_password,
            request.timeout,
        )

        # Step 2: Pre-check — collect running config per interface
        for intf in request.interfaces:
            resp = await conn.send_command(f"show running-config interface {intf}")
            config_text = resp.result
            pre_state[intf] = config_text

            # Validate: no trunks, no channel-group
            err = _check_trunk_or_channel(config_text, intf)
            if err:
                await safe_close(conn)
                return AuditRecord(
                    id=audit_id,
                    timestamp=datetime.now(UTC),
                    device_id=request.device_id,
                    device_ip=request.device_ip,
                    platform=request.platform,
                    operation="vlan_change",
                    status=AdvancedStatus.FAILED,
                    pre_state=pre_state,
                    error=err,
                )

        # Verify VLAN exists on device
        vlan_resp = await conn.send_command("show vlan brief")
        if str(request.target_vlan) not in vlan_resp.result:
            await safe_close(conn)
            return AuditRecord(
                id=audit_id,
                timestamp=datetime.now(UTC),
                device_id=request.device_id,
                device_ip=request.device_ip,
                platform=request.platform,
                operation="vlan_change",
                status=AdvancedStatus.FAILED,
                pre_state=pre_state,
                error=f"VLAN {request.target_vlan} does not exist on device",
            )

        # Step 3: Apply
        write_mem = request.write_memory
        if settings.advanced_require_write_mem:
            write_mem = True
        cmds = generate_vlan_commands(
            request.interfaces,
            request.target_vlan,
            request.description,
            write_mem,
            request.platform,
        )
        commands_sent = cmds
        await conn.send_configs(cmds)

        # Step 4: Post-check — verify changes took effect
        verify_cmd = "show interfaces status"
        if request.platform and "nxos" in request.platform.lower():
            verify_cmd = "show interface status"
        post_resp = await conn.send_command(verify_cmd)
        post_output = post_resp.result

        all_verified = True
        for intf in request.interfaces:
            old_vlan = _extract_current_vlan(pre_state.get(intf, ""))
            new_vlan = _parse_intf_status_line(post_output, intf)
            verified = new_vlan == str(request.target_vlan)
            if not verified:
                all_verified = False
            changes.append(
                PortChange(
                    interface=intf,
                    field="access_vlan",
                    old_value=old_vlan,
                    new_value=new_vlan or str(request.target_vlan),
                    verified=verified,
                )
            )

        # Collect post-state
        post_state: dict[str, str] = {}
        for intf in request.interfaces:
            resp = await conn.send_command(f"show running-config interface {intf}")
            post_state[intf] = resp.result

        await safe_close(conn)

        if not all_verified:
            # Auto-rollback
            rollback_cmds = generate_rollback_commands(pre_state, write_mem, request.platform)
            conn2 = await _connect(
                request.device_ip,
                request.username,
                request.password,
                request.enable_password,
                request.timeout,
            )
            try:
                await conn2.send_configs(rollback_cmds)
            finally:
                await safe_close(conn2)

            return AuditRecord(
                id=audit_id,
                timestamp=datetime.now(UTC),
                device_id=request.device_id,
                device_ip=request.device_ip,
                platform=request.platform,
                operation="vlan_change",
                status=AdvancedStatus.ROLLED_BACK,
                changes=changes,
                commands_sent=commands_sent,
                pre_state=pre_state,
                post_state=post_state,
                rollback_commands=rollback_cmds,
                error="Post-check verification failed — auto-rollback applied",
            )

        return AuditRecord(
            id=audit_id,
            timestamp=datetime.now(UTC),
            device_id=request.device_id,
            device_ip=request.device_ip,
            platform=request.platform,
            operation="vlan_change",
            status=AdvancedStatus.SUCCESS,
            changes=changes,
            commands_sent=commands_sent,
            pre_state=pre_state,
            post_state=post_state,
            rollback_commands=generate_rollback_commands(pre_state, write_mem, request.platform),
        )

    except Exception as exc:
        if conn is not None:
            await safe_close(conn)
        return AuditRecord(
            id=audit_id,
            timestamp=datetime.now(UTC),
            device_id=request.device_id,
            device_ip=request.device_ip,
            platform=request.platform,
            operation="vlan_change",
            status=AdvancedStatus.FAILED,
            commands_sent=commands_sent,
            pre_state=pre_state,
            error=str(exc),
        )


async def undo_change(
    original: AuditRecord,
    username: str,
    password: str,
    enable_password: str | None = None,
    timeout: int = 30,
) -> AuditRecord:
    """Undo a previous VLAN change by applying its rollback commands."""
    if not original.rollback_commands:
        return AuditRecord(
            id=str(uuid4()),
            timestamp=datetime.now(UTC),
            device_id=original.device_id,
            device_ip=original.device_ip,
            platform=original.platform,
            operation="undo",
            status=AdvancedStatus.FAILED,
            undo_of=original.id,
            error="No rollback commands available for this record",
        )

    if original.undone_by is not None:
        return AuditRecord(
            id=str(uuid4()),
            timestamp=datetime.now(UTC),
            device_id=original.device_id,
            device_ip=original.device_ip,
            platform=original.platform,
            operation="undo",
            status=AdvancedStatus.FAILED,
            undo_of=original.id,
            error=f"Change was already undone by {original.undone_by}",
        )

    lock = _get_device_lock(original.device_id)
    audit_id = str(uuid4())

    async with lock:
        conn: Any = None
        try:
            conn = await _connect(
                original.device_ip,
                username,
                password,
                enable_password,
                timeout,
            )
            await conn.send_configs(original.rollback_commands)
            await safe_close(conn)

            return AuditRecord(
                id=audit_id,
                timestamp=datetime.now(UTC),
                device_id=original.device_id,
                device_ip=original.device_ip,
                platform=original.platform,
                operation="undo",
                status=AdvancedStatus.SUCCESS,
                commands_sent=original.rollback_commands,
                undo_of=original.id,
            )
        except Exception as exc:
            if conn is not None:
                await safe_close(conn)
            return AuditRecord(
                id=audit_id,
                timestamp=datetime.now(UTC),
                device_id=original.device_id,
                device_ip=original.device_ip,
                platform=original.platform,
                operation="undo",
                status=AdvancedStatus.FAILED,
                undo_of=original.id,
                error=str(exc),
            )
