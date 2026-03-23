"""NetScope — FastAPI application."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse as StarletteJSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.audit_store import make_audit_store
from backend.auth import (
    AuthContext,
    hash_api_key,
    set_auth_store,
)
from backend.auth_store import make_auth_store
from backend.config import settings
from backend.logging_config import setup_logging
from backend.models import (
    TopologyResult,
)
from backend.playbook_store import make_playbook_store
from backend.settings_store import make_settings_store
from backend.store import store

_log_buffer = setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

# Track process start time for uptime reporting
_start_time = time.monotonic()
_start_timestamp = datetime.now(UTC)

# ---------------------------------------------------------------------------
# Optional stores for diff/rediscovery (only when SQLite is configured)
# ---------------------------------------------------------------------------

_req_store = None
_diff_store = None
_search_conn = None  # sqlite3.Connection used for FTS5 search index
_alert_rule_store = None
_alert_store = None
_http_alert_client = None  # httpx client for webhook delivery

# ---------------------------------------------------------------------------
# Auth stores and credential vault
# ---------------------------------------------------------------------------

_auth_store = make_auth_store()
set_auth_store(_auth_store)  # inject into auth module (avoids circular import)

_credential_vault = None
if settings.secret_key:
    from backend.credential_vault import CredentialVault

    _credential_vault = CredentialVault(settings.secret_key)
elif settings.auth_enabled:
    logger.warning(
        "NETSCOPE_AUTH_ENABLED=true but NETSCOPE_SECRET_KEY is not set"
        " — credential encryption disabled"
    )

if settings.db_path:
    from backend.store_sqlite import (
        SQLiteAlertRuleStore,
        SQLiteAlertStore,
        SQLiteDiffStore,
        SQLiteDiscoverRequestStore,
        _open_db,
    )

    _db_path = Path(settings.db_path)
    _req_store = SQLiteDiscoverRequestStore(_db_path, vault=_credential_vault)
    _diff_store = SQLiteDiffStore(_db_path)
    _search_conn = _open_db(_db_path)  # reuse same DB file for FTS5
    _alert_rule_store = SQLiteAlertRuleStore(_db_path)
    _alert_store = SQLiteAlertStore(_db_path)
    _settings_db_conn = _open_db(_db_path)
else:
    _settings_db_conn = None  # type: ignore[assignment]

# Settings store — SQLite-backed if db_path is set, otherwise in-memory
_settings_store = make_settings_store(_settings_db_conn)

# Audit and playbook stores
_audit_store = make_audit_store()
_playbook_store = make_playbook_store()


async def _load_builtin_playbooks() -> None:
    """Load built-in playbook templates into the store on startup."""
    try:
        from backend.playbook_loader import load_builtin_playbooks

        builtins = load_builtin_playbooks()
        for pb in builtins:
            existing = _playbook_store.get_playbook(pb.id)
            if existing is None:
                await _playbook_store.save_playbook(pb)
                logger.info("Loaded builtin playbook: %s", pb.title)
    except Exception:
        logger.exception("Failed to load builtin playbooks")


# ---------------------------------------------------------------------------
# Lifespan (scheduler)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _http_alert_client
    from backend.alerts import HttpxAlertClient

    _http_alert_client = HttpxAlertClient()

    # Expose module-level stores on app.state so router modules can access them
    app.state.http_alert_client = _http_alert_client
    app.state.req_store = _req_store
    app.state.diff_store = _diff_store
    app.state.search_conn = _search_conn
    app.state.alert_rule_store = _alert_rule_store
    app.state.alert_store = _alert_store
    app.state.audit_store = _audit_store
    app.state.auth_store = _auth_store
    app.state.credential_vault = _credential_vault
    app.state.settings_store = _settings_store
    app.state.log_buffer = _log_buffer
    app.state.start_time = _start_time
    app.state.start_timestamp = _start_timestamp
    app.state.playbook_store = _playbook_store
    app.state.playbook_runs = {}

    # Run retention cleanup on startup if SQLite is configured
    if _search_conn is not None and settings.snapshot_retention_days > 0:
        from backend.store_sqlite import cleanup_old_snapshots

        deleted = cleanup_old_snapshots(_search_conn, settings.snapshot_retention_days)
        if deleted:
            logger.info("Startup retention cleanup: deleted %d old snapshot(s)", deleted)

    task: asyncio.Task[None] | None = None
    if settings.rediscovery_interval > 0 and settings.db_path:
        from backend.scheduler import start_scheduler

        task = start_scheduler(
            settings.rediscovery_interval,
            Path(settings.db_path),
            settings.snapshot_retention_days,
        )
        logger.info("Scheduled re-discovery enabled: interval=%ds", settings.rediscovery_interval)
    elif settings.rediscovery_interval > 0:
        logger.warning(
            "NETSCOPE_REDISCOVERY_INTERVAL set but NETSCOPE_DB_PATH is not — scheduler disabled"
        )
    # Load built-in playbook templates
    await _load_builtin_playbooks()

    # Bootstrap default admin user if configured and no users exist
    if _auth_store is not None and settings.default_admin_password:
        from backend.models import APIKey as APIKeyModel
        from backend.models import User as UserModel
        from backend.models import UserRole

        existing = _auth_store.get_user_by_username("admin")
        if existing is None:
            from backend.auth import generate_api_key, hash_api_key, hash_password

            admin_user = UserModel(
                id=str(uuid4()),
                username="admin",
                password_hash=hash_password(settings.default_admin_password),
                role=UserRole.ADMIN,
                created_at=datetime.now(UTC),
            )
            await _auth_store.create_user(admin_user)

            raw_key = generate_api_key()
            api_key = APIKeyModel(
                id=str(uuid4()),
                key_hash=hash_api_key(raw_key),
                label="bootstrap-admin-key",
                user_id=admin_user.id,
                role=UserRole.ADMIN,
                created_at=datetime.now(UTC),
            )
            await _auth_store.create_api_key(api_key)
            logger.info("Bootstrapped admin user. API key: %s...", raw_key[:10])

    yield
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if _http_alert_client is not None:
        await _http_alert_client.aclose()


_OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "Health", "description": "Service health and log endpoints."},
    {"name": "Settings", "description": "Application configuration management."},
    {"name": "Auth", "description": "Authentication, user management, and API keys."},
    {"name": "Discovery", "description": "BFS network discovery and device probing."},
    {"name": "Sessions", "description": "Discovery session storage and retrieval."},
    {"name": "Search", "description": "Full-text search across discovered topology."},
    {"name": "Alerts", "description": "Alert rules, fired alerts, and webhook testing."},
    {"name": "Config Dump", "description": "SSH-based running-config collection."},
    {"name": "Export", "description": "Multi-format topology export."},
    {"name": "Backup", "description": "Database backup/restore and session import/export."},
    {"name": "Advanced", "description": "Live VLAN changes with audit trail."},
    {"name": "Playbooks", "description": "Command playbook management and execution."},
    {"name": "Saved Views", "description": "Named topology views with layout and annotations."},
]

app = FastAPI(
    title="NetScope",
    summary="SSH-based network topology intelligence for Cisco networks.",
    description=(
        "NetScope discovers network topology via SSH (CDP/LLDP), collects device state "
        "(interfaces, VLANs, ARP, MAC, routes, STP, VXLAN/EVPN), and provides a real-time "
        "interactive topology map.\n\n"
        "## Features\n"
        "- **BFS Discovery** — Walk the network from seed devices via CDP/LLDP neighbors.\n"
        "- **Multi-protocol** — CDP-prefer, LLDP-prefer, or both.\n"
        "- **Session Diffing** — Compare topology snapshots over time.\n"
        "- **Multi-format Export** — Draw.io, CSV, Excel, DOT, SVG, JSON.\n"
        "- **Advanced Mode** — Live VLAN changes with full audit trail and undo.\n"
        "- **Playbooks** — Reusable command templates with dry-run and rollback.\n"
        "- **Alerts** — Configurable rules with webhook delivery.\n"
    ),
    version="1.0.1",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=_OPENAPI_TAGS,
    lifespan=_lifespan,
)

# Expose module-level stores on app.state so router modules can access them.
# These are set here (at import time) so that TestClient without lifespan still works,
# and re-set inside _lifespan() for values that change there (e.g. _http_alert_client).
app.state.req_store = _req_store
app.state.diff_store = _diff_store
app.state.search_conn = _search_conn
app.state.alert_rule_store = _alert_rule_store
app.state.alert_store = _alert_store
app.state.auth_store = _auth_store
app.state.credential_vault = _credential_vault
app.state.settings_store = _settings_store
app.state.log_buffer = _log_buffer
app.state.start_time = _start_time
app.state.start_timestamp = _start_timestamp
app.state.http_alert_client = _http_alert_client
app.state.audit_store = _audit_store
app.state.playbook_store = _playbook_store
app.state.playbook_runs = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.rate_limit import limiter  # noqa: E402

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# Auth middleware (pure ASGI — no BaseHTTPMiddleware overhead)
# ---------------------------------------------------------------------------

_AUTH_EXEMPT_PATHS = {
    "/health",
    "/api/v1/health",
    "/auth/login",
    "/api/v1/auth/login",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
}
_AUTH_EXEMPT_PREFIXES = ("/assets/",)


class AuthMiddleware:
    """Pure ASGI middleware — validates tokens and sets request.state.auth_context."""

    def __init__(self, inner: ASGIApp) -> None:
        self.app = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.auth_enabled:
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        if path in _AUTH_EXEMPT_PATHS or any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Extract token from headers
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()
        token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
        if not token:
            token = headers.get(b"x-api-key", b"").decode()

        if not token:
            resp = StarletteJSONResponse(
                status_code=401,
                content={"detail": "Missing authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            await resp(scope, receive, send)
            return

        key_hash = hash_api_key(token)
        api_key = _auth_store.get_api_key_by_hash(key_hash) if _auth_store else None
        if api_key is None or api_key.disabled:
            resp = StarletteJSONResponse(
                status_code=401,
                content={"detail": "Invalid or disabled API key"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            await resp(scope, receive, send)
            return

        if api_key.expires_at is not None:
            if datetime.now(UTC) > api_key.expires_at:
                resp = StarletteJSONResponse(
                    status_code=401, content={"detail": "API key has expired"}
                )
                await resp(scope, receive, send)
                return

        user = _auth_store.get_user(api_key.user_id) if _auth_store else None
        if user is None or user.disabled:
            resp = StarletteJSONResponse(
                status_code=401, content={"detail": "User account disabled or not found"}
            )
            await resp(scope, receive, send)
            return

        # Store auth context for downstream dependencies
        scope.setdefault("state", {})["auth_context"] = AuthContext(
            user_id=user.id, username=user.username, role=user.role, via_api_key=True
        )

        await self.app(scope, receive, send)


app.add_middleware(AuthMiddleware)

STATIC_DIR = Path(settings.static_dir)

# ---------------------------------------------------------------------------
# Versioned API router — all endpoints served under /api/v1/
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Register versioned API router
# ---------------------------------------------------------------------------

from backend.routers.advanced import router as advanced_router  # noqa: E402
from backend.routers.alerts import router as alerts_router  # noqa: E402
from backend.routers.auth import router as auth_router  # noqa: E402
from backend.routers.config_dump import router as config_dump_router  # noqa: E402
from backend.routers.discovery import router as discovery_router  # noqa: E402
from backend.routers.export import router as export_router  # noqa: E402
from backend.routers.health import router as health_router  # noqa: E402
from backend.routers.playbooks import router as playbooks_router  # noqa: E402
from backend.routers.sessions import router as sessions_router  # noqa: E402
from backend.routers.views import router as views_router  # noqa: E402

router.include_router(health_router)
router.include_router(auth_router)
router.include_router(discovery_router)
router.include_router(sessions_router)
router.include_router(alerts_router)
router.include_router(config_dump_router)
router.include_router(export_router)
router.include_router(advanced_router)
router.include_router(playbooks_router)
router.include_router(views_router)

app.include_router(router)


# Root /health alias (load-balancer friendly — not versioned)
@app.get("/health", include_in_schema=False)
async def health_root(request: Request) -> dict[str, object]:
    """Unversioned health alias for load-balancer probes."""
    from backend.routers.health import health

    return await health(request)


# ---------------------------------------------------------------------------
# Frontend static files (production)
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    # Serve hashed JS/CSS bundles — Vite always outputs these under assets/
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Serve real files (favicon.ico, robots.txt, …) if they exist in dist/
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        # All other paths → index.html so Vue Router handles client-side routing
        return FileResponse(STATIC_DIR / "index.html")

else:

    @app.get("/", include_in_schema=False)
    async def root() -> HTMLResponse:
        return HTMLResponse(
            "<h1>NetScope API</h1><p>Frontend not built. Run <code>npm run build</code> in frontend/.</p>"  # noqa: E501
            "<p><a href='/api/docs'>API Docs</a></p>"
        )


def _get_session_or_404(session_id: str) -> TopologyResult:
    result = store.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    return result
