"""Playbook models and variable interpolation engine.

Defines the Configuration Playbook data structures:
- ``Playbook`` — a reusable, parameterized command sequence
- ``PlaybookVariable`` — typed variable definition with validation
- ``PlaybookExecution`` — immutable record of a playbook run
- Variable interpolation (``{{var}}`` substitution with strict validation)
- Command safety validation (blocked command list)
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from backend.config import settings

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VariableType(StrEnum):
    STRING = "string"
    INT = "int"
    CHOICE = "choice"
    INTERFACE = "interface"


class PlaybookCategory(StrEnum):
    VLAN = "vlan"
    SECURITY = "security"
    QOS = "qos"
    ACCESS_CONTROL = "access-control"
    MONITORING = "monitoring"
    MANAGEMENT = "management"
    ROUTING = "routing"
    GENERAL = "general"


class Platform(StrEnum):
    IOSXE = "iosxe"
    NXOS = "nxos"
    CBS = "cbs"


class ConfigMode(StrEnum):
    MERGE = "merge"
    REPLACE = "replace"


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PlaybookVariable(BaseModel):
    """A typed variable definition within a playbook."""

    name: str = Field(min_length=1, max_length=64)
    var_type: VariableType = VariableType.STRING
    required: bool = True
    default: str | None = None
    description: str | None = None
    choices: list[str] = []  # only used when var_type == CHOICE

    @field_validator("name")
    @classmethod
    def name_is_identifier(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError(f"Variable name must be a valid identifier: {v!r}")
        return v


class Playbook(BaseModel):
    """A reusable, parameterized configuration command sequence."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: PlaybookCategory = PlaybookCategory.GENERAL
    platforms: list[Platform] = [Platform.IOSXE]
    variables: list[PlaybookVariable] = []
    pre_checks: list[str] = []  # show commands before apply
    steps: list[str] = Field(min_length=1)  # config commands with {{var}} placeholders
    post_checks: list[str] = []  # show commands after apply
    rollback: list[str] = []  # explicit rollback commands
    config_mode: ConfigMode = ConfigMode.MERGE  # merge (default) or replace (IOS-XE 16.x+)
    builtin: bool = False  # True for system-provided templates
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlaybookCreateRequest(BaseModel):
    """Request body for creating a new playbook."""

    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: PlaybookCategory = PlaybookCategory.GENERAL
    platforms: list[Platform] = [Platform.IOSXE]
    variables: list[PlaybookVariable] = []
    pre_checks: list[str] = []
    steps: list[str] = Field(min_length=1)
    post_checks: list[str] = []
    rollback: list[str] = []
    config_mode: ConfigMode = ConfigMode.MERGE


class PlaybookUpdateRequest(BaseModel):
    """Request body for updating an existing playbook (all fields optional)."""

    title: str | None = None
    description: str | None = None
    category: PlaybookCategory | None = None
    platforms: list[Platform] | None = None
    variables: list[PlaybookVariable] | None = None
    pre_checks: list[str] | None = None
    steps: list[str] | None = None
    post_checks: list[str] | None = None
    rollback: list[str] | None = None
    config_mode: ConfigMode | None = None


class PlaybookDryRunRequest(BaseModel):
    """Request to preview interpolated commands without executing."""

    variables: dict[str, str] = {}
    device_ip: str | None = None  # when set with credentials, enables config diff
    device_platform: str | None = None
    username: str | None = None
    password: str | None = None
    enable_password: str | None = None
    timeout: int = 30


class PlaybookExecuteRequest(BaseModel):
    """Request to execute a playbook against device(s)."""

    device_ids: list[str] = Field(min_length=1)
    device_ips: dict[str, str]  # device_id -> IP address
    device_platforms: dict[str, str] = {}  # device_id -> platform string
    variables: dict[str, str] = {}
    write_memory: bool = False
    # Credentials (session-scoped, not stored)
    username: str
    password: str
    enable_password: str | None = None
    timeout: int = Field(default=30, ge=5, le=120)


class DeviceExecutionResult(BaseModel):
    """Result of executing a playbook on a single device."""

    device_id: str
    device_ip: str
    status: ExecutionStatus
    pre_check_outputs: dict[str, str] = {}  # command -> output
    commands_sent: list[str] = []
    post_check_outputs: dict[str, str] = {}  # command -> output
    rollback_commands: list[str] = []
    error: str | None = None


class PlaybookExecution(BaseModel):
    """Immutable record of a playbook execution run."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    playbook_id: str
    playbook_title: str
    timestamp: datetime
    variables: dict[str, str] = {}
    device_results: list[DeviceExecutionResult] = []
    overall_status: ExecutionStatus
    error: str | None = None


class PlaybookUndoRequest(BaseModel):
    """Credentials for undoing a playbook execution."""

    username: str
    password: str
    enable_password: str | None = None
    timeout: int = Field(default=30, ge=5, le=120)


class ConfigReplaceRequest(BaseModel):
    """Request to execute IOS-XE configure replace."""

    device_ip: str
    config_url: str = Field(
        description="IOS-XE config URL, e.g. flash:backup-config",
    )
    device_platform: str | None = None
    username: str
    password: str
    enable_password: str | None = None
    timeout: int = Field(default=30, ge=5, le=120)


# ---------------------------------------------------------------------------
# Variable interpolation
# ---------------------------------------------------------------------------

_VAR_PATTERN = re.compile(r"\{\{(\s*\??\w+\s*)\}\}")

# Control characters (ASCII 0-31) that must never appear in variable values.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")

# Maximum length for any variable value.
_MAX_VARIABLE_VALUE_LENGTH = 256

# Pattern for INTERFACE type validation (e.g., Gi1/0/1, Ethernet0/1, Vlan100).
_INTERFACE_PATTERN = re.compile(r"^[A-Za-z]+[0-9/.\-]+$")


def _sanitize_variable_value(name: str, value: str) -> str:
    """Validate a variable value is safe for command interpolation.

    Rejects control characters and enforces max length.
    Raises ``ValueError`` on invalid input.
    """
    if _CONTROL_CHAR_RE.search(value):
        raise ValueError(f"Variable {name!r} contains control characters (newlines, tabs, etc.)")
    if len(value) > _MAX_VARIABLE_VALUE_LENGTH:
        raise ValueError(
            f"Variable {name!r} exceeds maximum length of {_MAX_VARIABLE_VALUE_LENGTH} characters"
        )
    return value


class _SkipCommand(Exception):
    """Raised when a ``{{?var}}`` placeholder resolves to empty — skip the command."""


def interpolate(template: str, variables: dict[str, str]) -> str:
    """Replace ``{{var}}`` placeholders with values from *variables*.

    Use ``{{?var}}`` for optional variables: if the value is empty or missing,
    raises ``_SkipCommand`` so ``interpolate_commands`` can drop the line.

    Raises ``ValueError`` if a required variable is not provided
    or if a value contains unsafe characters.
    """

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        optional = raw.startswith("?")
        name = raw.lstrip("?")
        if optional:
            value = variables.get(name, "")
            if not value:
                raise _SkipCommand()
            return _sanitize_variable_value(name, value)
        if name not in variables:
            raise ValueError(f"Variable {{{{{name}}}}} is not provided")
        return _sanitize_variable_value(name, variables[name])

    return _VAR_PATTERN.sub(_replace, template)


def interpolate_commands(commands: list[str], variables: dict[str, str]) -> list[str]:
    """Interpolate a list of command templates.

    Commands containing ``{{?var}}`` placeholders are silently dropped
    when the variable is empty or not provided.
    """
    result: list[str] = []
    for cmd in commands:
        try:
            result.append(interpolate(cmd, variables))
        except _SkipCommand:
            continue
    return result


def validate_variables(
    playbook: Playbook,
    provided: dict[str, str],
) -> list[str]:
    """Validate provided variables against playbook definitions.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []
    defined_names = {v.name for v in playbook.variables}

    # Check for unknown variables
    for name in provided:
        if name not in defined_names:
            errors.append(f"Unknown variable: {name!r}")

    # Check required variables and type validation
    for var_def in playbook.variables:
        value = provided.get(var_def.name)
        if value is None or value == "":
            if var_def.required and var_def.default is None:
                errors.append(f"Required variable {var_def.name!r} is missing")
            continue

        # Universal safety checks: control characters and max length
        if _CONTROL_CHAR_RE.search(value):
            errors.append(
                f"Variable {var_def.name!r} contains control characters (newlines, tabs, etc.)"
            )
            continue
        if len(value) > _MAX_VARIABLE_VALUE_LENGTH:
            errors.append(
                f"Variable {var_def.name!r} exceeds maximum length"
                f" of {_MAX_VARIABLE_VALUE_LENGTH} characters"
            )
            continue

        if var_def.var_type == VariableType.INT:
            try:
                int(value)
            except ValueError:
                errors.append(f"Variable {var_def.name!r} must be an integer, got {value!r}")

        if var_def.var_type == VariableType.CHOICE and var_def.choices:
            if value not in var_def.choices:
                errors.append(
                    f"Variable {var_def.name!r} must be one of {var_def.choices}, got {value!r}"
                )

        if var_def.var_type == VariableType.INTERFACE:
            if not _INTERFACE_PATTERN.match(value):
                errors.append(
                    f"Variable {var_def.name!r} must be a valid interface name"
                    f" (e.g., Gi1/0/1, Ethernet0/1), got {value!r}"
                )

    return errors


def resolve_variables(
    playbook: Playbook,
    provided: dict[str, str],
) -> dict[str, str]:
    """Merge provided values with defaults.

    Returns the complete variable dict for interpolation.
    """
    resolved: dict[str, str] = {}
    for var_def in playbook.variables:
        value = provided.get(var_def.name)
        if value is None or value == "":
            if var_def.default is not None:
                resolved[var_def.name] = var_def.default
        else:
            resolved[var_def.name] = value
    return resolved


# ---------------------------------------------------------------------------
# Command safety validation
# ---------------------------------------------------------------------------

# Default blocked command patterns (case-insensitive prefix match)
_DEFAULT_BLOCKED = [
    "erase",
    "reload",
    "write erase",
    "delete",
    "format",
    "squeeze",
]


def get_blocked_commands() -> list[str]:
    """Return the blocked command list from settings or default."""
    raw = getattr(settings, "playbook_blocked_commands", "")
    if raw:
        return [c.strip().lower() for c in raw.split(",") if c.strip()]
    return [c.lower() for c in _DEFAULT_BLOCKED]


def validate_command_safety(commands: list[str]) -> list[str]:
    """Check commands against the blocked list.

    Returns list of error messages (empty if all safe).
    """
    blocked = get_blocked_commands()
    errors: list[str] = []
    for cmd in commands:
        cmd_lower = cmd.strip().lower()
        for b in blocked:
            if cmd_lower.startswith(b):
                errors.append(f"Blocked command: {cmd!r} (matches {b!r})")
                break
    return errors
