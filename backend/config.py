import logging
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

_config_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    log_level: Literal["debug", "info", "warning", "error", "critical"] = "info"
    max_sessions: int = Field(default=50, ge=1, le=1000)
    static_dir: str = "frontend/dist"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8000"]
    rate_limit_enabled: bool = True
    # When set, sessions and config dumps are persisted to SQLite at this path.
    # If unset, in-memory LRU is used.
    db_path: str | None = None
    # Automatic re-discovery interval in seconds (0 = disabled).
    # Requires NETSCOPE_DB_PATH so that the original DiscoverRequest is stored.
    rediscovery_interval: int = Field(default=0, ge=0)
    # Snapshot retention in days (0 = keep forever). Snapshots older than this
    # are purged on startup and after each scheduled re-discovery pass.
    snapshot_retention_days: int = Field(default=90, ge=0)

    # Advanced Mode (write operations)
    allow_advanced: bool = False
    advanced_password: str = ""
    advanced_require_write_mem: bool = False
    audit_retention_days: int = Field(default=90, ge=0)
    advanced_max_ports_per_change: int = Field(default=48, ge=1, le=96)

    # Playbooks
    playbook_max_targets: int = Field(default=10, ge=1, le=100)
    playbook_blocked_commands: str = ""  # comma-separated; uses defaults if empty
    playbook_require_dry_run: bool = True

    # Authentication
    secret_key: str = ""  # Master key for Fernet encryption + token signing
    auth_enabled: bool = False  # When True, all API endpoints require a valid token
    default_admin_password: str = ""  # If set, bootstrap an admin user on first startup

    @model_validator(mode="after")
    def _check_secret_key(self) -> "Settings":
        if self.auth_enabled and not self.secret_key:
            raise ValueError("NETSCOPE_SECRET_KEY is required when authentication is enabled")
        if self.db_path and not self.secret_key:
            _config_logger.warning(
                "NETSCOPE_DB_PATH is set but NETSCOPE_SECRET_KEY is empty — "
                "credential and config-dump encryption is disabled"
            )
        if self.allow_advanced and not self.advanced_password:
            _config_logger.warning(
                "NETSCOPE_ALLOW_ADVANCED is True but NETSCOPE_ADVANCED_PASSWORD is empty — "
                "advanced operations (VLAN changes, etc.) are unprotected"
            )
        return self

    model_config = {"env_prefix": "NETSCOPE_"}


settings = Settings()
