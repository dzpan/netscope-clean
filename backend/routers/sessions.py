"""Sessions, Search, Snapshots, and Diff router endpoints."""

from __future__ import annotations

import logging
from collections import Counter

from fastapi import APIRouter, HTTPException, Request

import backend.store as _store_module
from backend.diff import compute_diff
from backend.discovery import run_discovery
from backend.models import (
    CredentialSet,
    DeviceStatus,
    DiscoverySummary,
    FailureReasonCount,
    PathTraceRequest,
    PathTraceResult,
    PlatformCount,
    ProtocolCount,
    RediscoverRequest,
    ResolvePlaceholderRequest,
    SearchResponse,
    SnapshotMeta,
    StatusCount,
    TopologyDiff,
    TopologyResult,
    VlanMapEntry,
)
from backend.normalizer import build_vlan_map, reconcile_placeholders
from backend.routers._helpers import get_session_or_404
from backend.routers.discovery import rebuild_search_index
from backend.search import search_in_memory, search_index

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.get("/search", response_model=SearchResponse, tags=["Search"])
async def search(
    request: Request,
    q: str = "",
    session_id: str | None = None,
    limit: int = 50,
) -> SearchResponse:
    """Full-text search across all collected network data.

    Returns ranked results grouped by type: device, interface, mac, ip, vlan, route.
    Each result links back to a source device and discovery session.
    Supports partial matches and common network formats (CIDR, MAC with various delimiters).

    When NETSCOPE_DB_PATH is configured, uses SQLite FTS5 for fast ranked search.
    Otherwise falls back to a linear scan of the current in-memory sessions.
    """
    if not q.strip():
        return SearchResponse(query=q, total=0, results=[])

    limit = max(1, min(limit, 200))

    _search_conn = request.app.state.search_conn
    if _search_conn is not None:
        return search_index(_search_conn, q, session_id=session_id, limit=limit)

    # In-memory fallback
    sessions = _store_module.store.list_all()
    return search_in_memory(sessions, q, session_id=session_id, limit=limit)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[TopologyResult], tags=["Sessions"])
async def list_sessions() -> list[TopologyResult]:
    return _store_module.store.list_all()


@router.get("/sessions/{session_id}", response_model=TopologyResult, tags=["Sessions"])
async def get_session(session_id: str) -> TopologyResult:
    result = _store_module.store.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.get("/sessions/{session_id}/vlan-map", response_model=list[VlanMapEntry], tags=["Sessions"])
async def get_vlan_map(session_id: str) -> list[VlanMapEntry]:
    """Return network-wide VLAN summary for a discovery session."""
    result = get_session_or_404(session_id)
    return build_vlan_map(result.devices)


@router.get("/sessions/{session_id}/summary", response_model=DiscoverySummary, tags=["Sessions"])
async def get_session_summary(session_id: str) -> DiscoverySummary:
    """Return an aggregated discovery summary dashboard for a session."""
    result = get_session_or_404(session_id)
    return _build_summary(result)


@router.post(
    "/sessions/{session_id}/resolve-placeholder",
    response_model=TopologyResult,
    tags=["Sessions"],
)
async def resolve_placeholder(
    session_id: str,
    req: ResolvePlaceholderRequest,
) -> TopologyResult:
    """Manually resolve a placeholder device by updating its management IP.

    The placeholder's mgmt_ip is updated, then reconciliation is re-run so
    that if the new IP matches an already-discovered device the placeholder
    is merged automatically.
    """
    result = get_session_or_404(session_id)

    # Find the placeholder
    placeholder = next(
        (d for d in result.devices if d.id == req.placeholder_device_id),
        None,
    )
    if placeholder is None:
        raise HTTPException(status_code=404, detail="Placeholder device not found")
    if placeholder.status != DeviceStatus.PLACEHOLDER:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Device '{req.placeholder_device_id}' is not a placeholder"
                f" (status: {placeholder.status})"
            ),
        )

    # Update the placeholder's IP
    placeholder.mgmt_ip = req.mgmt_ip

    # Re-run reconciliation to merge if IP now matches a real device
    devices, links = reconcile_placeholders(result.devices, result.links)
    result = result.model_copy(update={"devices": devices, "links": links})

    # Persist updated result
    await _store_module.store.save(result)
    return result


def _build_summary(result: TopologyResult) -> DiscoverySummary:
    """Compute aggregated summary statistics from a TopologyResult."""
    ok_devices = [d for d in result.devices if d.status == DeviceStatus.OK]
    placeholder_devices = [d for d in result.devices if d.status == DeviceStatus.PLACEHOLDER]

    # Platform breakdown (OK devices only)
    platform_counts = Counter(d.platform or "Unknown" for d in ok_devices)
    platform_breakdown = [
        PlatformCount(platform=p, count=c) for p, c in platform_counts.most_common()
    ]

    # Status breakdown (all devices)
    status_counts = Counter(d.status for d in result.devices)
    status_breakdown = [StatusCount(status=s, count=c) for s, c in status_counts.most_common()]

    # Failure reason breakdown
    failure_counts = Counter(f.reason for f in result.failures)
    failure_breakdown = [
        FailureReasonCount(reason=r, count=c) for r, c in failure_counts.most_common()
    ]

    # Protocol breakdown for links
    proto_counts = Counter(lk.protocol for lk in result.links)
    protocol_breakdown = [ProtocolCount(protocol=p, count=c) for p, c in proto_counts.most_common()]

    # Port-channel links
    port_channel_links = sum(1 for lk in result.links if lk.port_channel)

    # VLAN count (unique VLANs across all OK devices)
    all_vlans: set[str] = set()
    for d in ok_devices:
        for v in d.vlans:
            all_vlans.add(v.vlan_id)

    # STP root bridges
    stp_root_count = sum(1 for d in ok_devices if any(stp.is_root for stp in d.stp_info))

    # Interface counts
    total_interfaces = 0
    up_interfaces = 0
    down_interfaces = 0
    for d in ok_devices:
        for intf in d.interfaces:
            total_interfaces += 1
            status = (intf.status or "").lower()
            if "up" in status:
                up_interfaces += 1
            elif "down" in status or "disabled" in status:
                down_interfaces += 1

    return DiscoverySummary(
        session_id=result.session_id,
        discovered_at=result.discovered_at,
        total_devices=len(result.devices),
        ok_devices=len(ok_devices),
        placeholder_devices=len(placeholder_devices),
        total_failures=len(result.failures),
        failure_breakdown=failure_breakdown,
        total_links=len(result.links),
        port_channel_links=port_channel_links,
        protocol_breakdown=protocol_breakdown,
        platform_breakdown=platform_breakdown,
        status_breakdown=status_breakdown,
        total_vlans=len(all_vlans),
        native_vlan_mismatches=len(result.native_vlan_mismatches),
        stp_root_bridges=stp_root_count,
        total_interfaces=total_interfaces,
        up_interfaces=up_interfaces,
        down_interfaces=down_interfaces,
    )


@router.post("/sessions/{session_id}/path-trace", response_model=PathTraceResult, tags=["Sessions"])
async def path_trace(session_id: str, req: PathTraceRequest) -> PathTraceResult:
    """Trace the L3 path from source to destination through the topology.

    Phase 1: routing-table only (no L2/ARP resolution yet).
    """
    from backend.path_trace import trace_path

    result = get_session_or_404(session_id)
    return trace_path(result, req)


# ---------------------------------------------------------------------------
# Snapshots (alias for sessions with lightweight metadata list)
# ---------------------------------------------------------------------------


@router.get("/snapshots", response_model=list[SnapshotMeta], tags=["Sessions"])
async def list_snapshots() -> list[SnapshotMeta]:
    """List all stored topology snapshots as lightweight metadata (no full device data).

    Suitable for populating a timeline or picker in the UI.
    Efficient when SQLite is configured — uses SQL JSON extraction instead of
    deserialising full result blobs.
    """
    # SQLiteSessionStore exposes list_meta() for efficient metadata-only queries
    sqlite_store = getattr(_store_module.store, "_conn", None)
    if sqlite_store is not None:
        from backend.store_sqlite import SQLiteSessionStore

        if isinstance(_store_module.store, SQLiteSessionStore):
            return _store_module.store.list_meta()

    # In-memory fallback: derive counts from already-loaded results
    return [
        SnapshotMeta(
            session_id=r.session_id,
            discovered_at=r.discovered_at,
            device_count=len(r.devices),
            link_count=len(r.links),
            failure_count=len(r.failures),
        )
        for r in _store_module.store.list_all()
    ]


@router.get("/snapshots/{snapshot_id}", response_model=TopologyResult, tags=["Sessions"])
async def get_snapshot(snapshot_id: str) -> TopologyResult:
    """Load a full topology snapshot by session ID."""
    return get_session_or_404(snapshot_id)


# ---------------------------------------------------------------------------
# Re-discovery and diff
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/rediscover", response_model=TopologyResult, tags=["Sessions"])
async def rediscover(
    request: Request, session_id: str, body: RediscoverRequest | None = None
) -> TopologyResult:
    """Re-run discovery with the original parameters (credentials may be overridden).

    The original DiscoverRequest is required — only available when NETSCOPE_DB_PATH is set.
    """
    _req_store = request.app.state.req_store
    if _req_store is None:
        raise HTTPException(
            status_code=422,
            detail="Re-discovery requires NETSCOPE_DB_PATH to be configured",
        )

    previous = get_session_or_404(session_id)
    original_req = _req_store.get(session_id)
    if original_req is None:
        raise HTTPException(
            status_code=404,
            detail="No stored discovery request for this session — cannot re-discover",
        )

    # Apply credential overrides from request body if provided
    if body is not None:
        new_cred_sets = body.credential_sets
        if not new_cred_sets and (body.username or body.password):
            new_cred_sets = [
                CredentialSet(
                    username=body.username or original_req.username,
                    password=body.password or original_req.password,
                    enable_password=body.enable_password or original_req.enable_password,
                )
            ]
        if new_cred_sets:
            original_req = original_req.model_copy(update={"credential_sets": new_cred_sets})

    logger.info("Re-discovery requested: session=%s seeds=%s", session_id, original_req.seeds)
    current = await run_discovery(original_req)
    await _store_module.store.save(current)
    await _req_store.save(current.session_id, original_req)
    rebuild_search_index(request.app.state.search_conn, current)

    # Compute and persist diff if SQLite diff store is available
    _diff_store = request.app.state.diff_store
    if _diff_store is not None:
        diff = compute_diff(current, previous)
        await _diff_store.save(diff)
        logger.info(
            "Diff computed: %d change(s) between %s → %s",
            diff.total_changes,
            previous.session_id,
            current.session_id,
        )
        await _maybe_fire_alerts(request, diff)

    logger.info(
        "Re-discovery complete: new_session=%s devices=%d links=%d",
        current.session_id,
        len(current.devices),
        len(current.links),
    )
    return current


async def _maybe_fire_alerts(request: Request, diff: TopologyDiff) -> None:
    """Evaluate alert rules against a diff and persist + deliver webhooks.

    No-op when alert stores are not configured (in-memory mode).
    """
    _alert_rule_store = request.app.state.alert_rule_store
    _alert_store = request.app.state.alert_store
    _http_alert_client = request.app.state.http_alert_client
    if _alert_rule_store is None or _alert_store is None or _http_alert_client is None:
        return
    from backend.alerts import fire_alerts

    rules = _alert_rule_store.list_all()
    if not rules:
        return
    alerts = await fire_alerts(diff, rules, _http_alert_client)
    for alert in alerts:
        await _alert_store.save(alert)
    if alerts:
        logger.info("Alerts fired: %d alert(s) for diff %s", len(alerts), diff.diff_id)


@router.get(
    "/sessions/{session_id}/diff/{previous_id}",
    response_model=TopologyDiff,
    tags=["Sessions"],
)
async def get_diff(request: Request, session_id: str, previous_id: str) -> TopologyDiff:
    """Return the topology diff between two snapshots.

    If a pre-computed diff exists in SQLite it is returned directly;
    otherwise the diff is computed on-the-fly from the two stored sessions.
    """
    _diff_store = request.app.state.diff_store
    # Try cached diff first
    if _diff_store is not None:
        cached = _diff_store.get_by_sessions(session_id, previous_id)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

    current = _store_module.store.get(session_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Current session not found")
    previous = _store_module.store.get(previous_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="Previous session not found")

    diff = compute_diff(current, previous)

    # Persist for future requests
    if _diff_store is not None:
        await _diff_store.save(diff)

    return diff
