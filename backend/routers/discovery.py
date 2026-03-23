"""Discovery router endpoints."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

import backend.store as _store_module
from backend.discovery import probe_device, run_discovery
from backend.models import (
    ArpEntry,
    ChannelMember,
    CredentialSet,
    Device,
    DeviceStatus,
    DiscoverRequest,
    DiscoveryProgress,
    EtherChannelInfo,
    EVPNNeighbor,
    Failure,
    InterfaceInfo,
    Link,
    MacTableEntry,
    NVEPeer,
    ProbeRequest,
    ProbeResult,
    RetryFailedRequest,
    RetryRequest,
    RouteEntry,
    STPPortInfo,
    STPVlanInfo,
    TopologyResult,
    VlanInfo,
    VNIMapping,
)
from backend.normalizer import normalize_links, reconcile_placeholders
from backend.rate_limit import limiter
from backend.routers._helpers import get_session_or_404
from backend.search import build_search_index

logger = logging.getLogger(__name__)

router = APIRouter()


def rebuild_search_index(search_conn: object, result: TopologyResult) -> None:
    """Rebuild FTS5 search index for a session (no-op when search_conn is None)."""
    if search_conn is not None:
        try:
            build_search_index(search_conn, result)  # type: ignore[arg-type]
        except Exception:
            logger.exception("Search index rebuild failed for session=%s", result.session_id)


@router.post("/discover", response_model=TopologyResult, tags=["Discovery"])
@limiter.limit("2/minute")
async def discover(request: Request, req: DiscoverRequest) -> TopologyResult:
    logger.info("Discovery requested: seeds=%s scope=%s", req.seeds, req.scope)
    result = await run_discovery(req)
    await _store_module.store.save(result)
    _req_store = request.app.state.req_store
    if _req_store is not None:
        await _req_store.save(result.session_id, req)
    rebuild_search_index(request.app.state.search_conn, result)
    logger.info(
        "Discovery complete: session=%s devices=%d links=%d failures=%d",
        result.session_id,
        len(result.devices),
        len(result.links),
        len(result.failures),
    )
    return result


@router.post("/retry", response_model=TopologyResult, tags=["Discovery"])
@limiter.limit("2/minute")
async def retry_auth(request: Request, req: RetryRequest) -> TopologyResult:
    """Re-run discovery on specific targets with new credentials, merge into existing session."""
    existing = get_session_or_404(req.session_id)

    mini_req = DiscoverRequest(
        seeds=req.targets,
        username=req.username,
        password=req.password,
        enable_password=req.enable_password,
        max_hops=req.max_hops,  # continue BFS from retried devices
        timeout=req.timeout,
        prefer_cdp=True,
    )
    retry_result = await run_discovery(mini_req)

    retry_ips = set(req.targets)

    # Merge devices: update existing with newly discovered.
    # Never downgrade a device that was previously ok — a subsequent BFS may
    # encounter it with the wrong credentials and mark it auth_failed again.
    devices: dict[str, Device] = {d.id: d for d in existing.devices}
    for d in retry_result.devices:
        prev = devices.get(d.id)
        if prev and prev.status == DeviceStatus.OK and d.status != DeviceStatus.OK:
            continue  # protect previously successful devices
        devices[d.id] = d

    # Build set of IPs/IDs that are now successfully discovered — protect them
    # from being re-added as failures (BFS may try them with wrong creds)
    ok_targets: set[str] = {
        t for d in devices.values() if d.status == DeviceStatus.OK for t in (d.mgmt_ip, d.id)
    }

    # Merge failures: drop retried IPs, add new results only for non-ok targets
    failures = [f for f in existing.failures if f.target not in retry_ips]
    for f in retry_result.failures:
        if f.target not in ok_targets:
            failures.append(f)

    # Merge links, reconcile placeholders with real devices (by IP match)
    merged_devices = list(devices.values())
    merged_links = normalize_links(existing.links + retry_result.links)
    merged_devices, merged_links = reconcile_placeholders(merged_devices, merged_links)

    merged = TopologyResult(
        session_id=existing.session_id,
        discovered_at=existing.discovered_at,
        devices=merged_devices,
        links=merged_links,
        failures=failures,
    )
    await _store_module.store.save(merged)
    rebuild_search_index(request.app.state.search_conn, merged)
    return merged


@router.post("/discover/stream", tags=["Discovery"])
@limiter.limit("2/minute")
async def discover_stream(req: DiscoverRequest, request: Request) -> StreamingResponse:
    """SSE-powered discovery: streams per-device progress events, then the final result."""
    logger.info("SSE Discovery requested: seeds=%s scope=%s", req.seeds, req.scope)

    progress_queue: asyncio.Queue[DiscoveryProgress] = asyncio.Queue()

    def on_progress(p: DiscoveryProgress) -> None:
        progress_queue.put_nowait(p)

    # Capture app state references for the generator closure
    _req_store = request.app.state.req_store
    _search_conn = request.app.state.search_conn

    async def event_generator() -> AsyncIterator[str]:
        task = asyncio.create_task(run_discovery(req, progress_callback=on_progress))

        while not task.done():
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                yield f"event: progress\ndata: {progress.model_dump_json()}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"

        # Drain remaining progress events
        while not progress_queue.empty():
            progress = progress_queue.get_nowait()
            yield f"event: progress\ndata: {progress.model_dump_json()}\n\n"

        try:
            result = task.result()
            # Yield the result to the client FIRST so the UI unblocks immediately,
            # then persist to store / search index in the background.
            result_json = result.model_dump_json()
            logger.info(
                "SSE Discovery complete: session=%s devices=%d links=%d failures=%d",
                result.session_id,
                len(result.devices),
                len(result.links),
                len(result.failures),
            )
            yield f"event: result\ndata: {result_json}\n\n"
        except Exception as exc:
            logger.exception("SSE Discovery failed")
            yield f"event: error\ndata: {exc!s}\n\n"
            return

        # Persist after the client has the result — failures here are non-fatal
        try:
            await _store_module.store.save(result)
            if _req_store is not None:
                await _req_store.save(result.session_id, req)
            rebuild_search_index(_search_conn, result)
        except Exception:
            logger.exception("Post-discovery persistence failed for session=%s", result.session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/retry-failed", response_model=TopologyResult, tags=["Discovery"])
@limiter.limit("2/minute")
async def retry_failed(request: Request, req: RetryFailedRequest) -> TopologyResult:
    """Retry all failed devices from a session, regardless of failure reason."""
    existing = get_session_or_404(req.session_id)

    # Filter failures by reason if specified
    failures_to_retry = existing.failures
    if req.reason_filter:
        failures_to_retry = [f for f in failures_to_retry if f.reason in req.reason_filter]

    if not failures_to_retry:
        return existing

    targets = [f.target for f in failures_to_retry]

    # Build credential list: explicit sets first, then primary
    cred_sets = list(req.credential_sets)
    if req.username:
        cred_sets.append(
            CredentialSet(
                username=req.username,
                password=req.password,
                enable_password=req.enable_password,
            )
        )
    # Fall back to original discovery credentials if available
    _req_store = request.app.state.req_store
    if _req_store is not None and not cred_sets:
        orig_req = _req_store.get(req.session_id)
        if orig_req:
            cred_sets = list(orig_req.credential_sets)
            if orig_req.username:
                cred_sets.append(
                    CredentialSet(
                        username=orig_req.username,
                        password=orig_req.password,
                        enable_password=orig_req.enable_password,
                    )
                )

    if not cred_sets:
        raise HTTPException(400, "No credentials provided and no saved credentials found")

    mini_req = DiscoverRequest(
        seeds=targets,
        credential_sets=cred_sets,
        max_hops=req.max_hops,
        timeout=req.timeout,
    )
    retry_result = await run_discovery(mini_req)

    retry_ips = set(targets)

    # Merge devices
    devices: dict[str, Device] = {d.id: d for d in existing.devices}
    for d in retry_result.devices:
        prev = devices.get(d.id)
        if prev and prev.status == DeviceStatus.OK and d.status != DeviceStatus.OK:
            continue
        devices[d.id] = d

    ok_targets: set[str] = {
        t for d in devices.values() if d.status == DeviceStatus.OK for t in (d.mgmt_ip, d.id)
    }

    # Merge failures
    failures = [f for f in existing.failures if f.target not in retry_ips]
    for f in retry_result.failures:
        if f.target not in ok_targets:
            failures.append(f)

    merged_devices = list(devices.values())
    merged_links = normalize_links(existing.links + retry_result.links)
    merged_devices, merged_links = reconcile_placeholders(merged_devices, merged_links)

    merged = TopologyResult(
        session_id=existing.session_id,
        discovered_at=existing.discovered_at,
        devices=merged_devices,
        links=merged_links,
        failures=failures,
    )
    await _store_module.store.save(merged)
    rebuild_search_index(request.app.state.search_conn, merged)
    return merged


@router.post("/probe", response_model=ProbeResult, tags=["Discovery"])
async def probe(req: ProbeRequest) -> ProbeResult:
    success, info = await probe_device(
        req.host, req.username, req.password, req.enable_password, req.timeout
    )
    return ProbeResult(
        host=req.host,
        success=success,
        hostname=info.get("hostname"),
        platform=info.get("platform"),
        os_version=info.get("os_version"),
        error=info.get("error"),
    )


@router.get("/demo", response_model=TopologyResult, tags=["Discovery"])
async def load_demo() -> TopologyResult:
    """Seed the session store with a realistic fake topology for UI testing."""
    result = TopologyResult(
        session_id=str(uuid4()),
        discovered_at=datetime.now(UTC),
        devices=[
            Device(
                id="CORE-SW-01",
                hostname="CORE-SW-01",
                mgmt_ip="10.0.0.1",
                platform="C9300-48P",
                serial="FCW2301A001",
                os_version="17.3.5",
                uptime="45 days, 3 hours, 22 minutes",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="GigabitEthernet1/0/1", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/2", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/3", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="TenGigabitEthernet1/1/1",
                        status="connected",
                        vlan="trunk",
                        speed="10G",
                    ),  # noqa: E501
                    InterfaceInfo(name="Vlan1", status="connected", ip_address="10.0.0.1"),
                    InterfaceInfo(name="Vlan100", status="connected", ip_address="10.0.100.1"),
                    InterfaceInfo(
                        name="GigabitEthernet1/0/48", status="notconnect", vlan="1", speed="auto"
                    ),  # noqa: E501
                ],
                vlans=[
                    VlanInfo(vlan_id="1", name="default", status="active"),
                    VlanInfo(vlan_id="10", name="Data", status="active"),
                    VlanInfo(vlan_id="20", name="Voice", status="active"),
                    VlanInfo(vlan_id="30", name="Wireless", status="active"),
                    VlanInfo(vlan_id="100", name="Management", status="active"),
                ],
                arp_table=[
                    ArpEntry(
                        ip_address="10.0.0.1",
                        mac_address="0cd5.d366.24cc",
                        interface="Vlan1",
                        entry_type="static",
                    ),  # noqa: E501
                    ArpEntry(
                        ip_address="10.0.1.1",
                        mac_address="aabb.ccdd.0001",
                        interface="Vlan1",
                        entry_type="dynamic",
                    ),  # noqa: E501
                    ArpEntry(
                        ip_address="10.0.1.2",
                        mac_address="aabb.ccdd.0002",
                        interface="Vlan1",
                        entry_type="dynamic",
                    ),  # noqa: E501
                    ArpEntry(
                        ip_address="10.0.0.254",
                        mac_address="dead.beef.cafe",
                        interface="Vlan1",
                        entry_type="dynamic",
                    ),  # noqa: E501
                ],
                mac_table=[
                    MacTableEntry(
                        mac_address="aabb.ccdd.0001",
                        vlan_id="1",
                        interface="Gi1/0/1",
                        entry_type="dynamic",
                    ),  # noqa: E501
                    MacTableEntry(
                        mac_address="aabb.ccdd.0002",
                        vlan_id="1",
                        interface="Gi1/0/2",
                        entry_type="dynamic",
                    ),  # noqa: E501
                    MacTableEntry(
                        mac_address="dead.beef.cafe",
                        vlan_id="1",
                        interface="Te1/1/1",
                        entry_type="dynamic",
                    ),  # noqa: E501
                    MacTableEntry(
                        mac_address="1122.3344.5566",
                        vlan_id="10",
                        interface="Gi1/0/3",
                        entry_type="dynamic",
                    ),  # noqa: E501
                ],
                route_table=[
                    RouteEntry(
                        protocol="C",
                        route_type="connected",
                        destination="10.0.0.0/24",
                        interface="Vlan1",
                    ),  # noqa: E501
                    RouteEntry(
                        protocol="L",
                        route_type="local",
                        destination="10.0.0.1/32",
                        interface="Vlan1",
                    ),  # noqa: E501
                    RouteEntry(
                        protocol="C",
                        route_type="connected",
                        destination="10.0.100.0/24",
                        interface="Vlan100",
                    ),  # noqa: E501
                    RouteEntry(
                        protocol="S",
                        route_type="static",
                        destination="0.0.0.0/0",
                        next_hop="10.0.0.254",
                        metric="1/0",
                    ),  # noqa: E501
                    RouteEntry(
                        protocol="S",
                        route_type="static",
                        destination="192.168.0.0/16",
                        next_hop="10.0.0.254",
                        metric="1/0",
                    ),  # noqa: E501
                ],
                etherchannels=[
                    EtherChannelInfo(
                        channel_id="1",
                        port_channel="Po1",
                        layer="Layer2",
                        status="up",
                        protocol="LACP",
                        members=[
                            ChannelMember(
                                interface="GigabitEthernet1/0/1", status="P", status_desc="bundled"
                            ),  # noqa: E501
                            ChannelMember(
                                interface="GigabitEthernet1/0/2", status="P", status_desc="bundled"
                            ),  # noqa: E501
                        ],
                    ),
                    EtherChannelInfo(
                        channel_id="2",
                        port_channel="Po2",
                        layer="Layer2",
                        status="down",
                        protocol="PAgP",
                        members=[
                            ChannelMember(
                                interface="GigabitEthernet1/0/3", status="D", status_desc="down"
                            ),  # noqa: E501
                        ],
                    ),
                ],
                stp_info=[
                    STPVlanInfo(
                        vlan_id="1",
                        protocol="rstp",
                        root_priority="32769",
                        root_address="0cd5.d366.2400",
                        root_cost="0",
                        is_root=True,
                        bridge_priority="32769",
                        bridge_address="0cd5.d366.2400",
                        ports=[
                            STPPortInfo(
                                interface="GigabitEthernet1/0/1",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.1",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/2",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.2",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/3",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.3",
                                link_type="P2p",
                            ),  # noqa: E501
                        ],
                    ),
                    STPVlanInfo(
                        vlan_id="10",
                        protocol="rstp",
                        root_priority="24586",
                        root_address="0cd5.d366.2400",
                        root_cost="0",
                        is_root=True,
                        bridge_priority="24586",
                        bridge_address="0cd5.d366.2400",
                        ports=[
                            STPPortInfo(
                                interface="GigabitEthernet1/0/1",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.1",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/2",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.2",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/3",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.3",
                                link_type="P2p",
                            ),  # noqa: E501
                        ],
                    ),
                    STPVlanInfo(
                        vlan_id="20",
                        protocol="rstp",
                        root_priority="24596",
                        root_address="0cd5.d366.2400",
                        root_cost="0",
                        is_root=True,
                        bridge_priority="24596",
                        bridge_address="0cd5.d366.2400",
                        ports=[
                            STPPortInfo(
                                interface="GigabitEthernet1/0/1",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.1",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/2",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.2",
                                link_type="P2p",
                            ),  # noqa: E501
                        ],
                    ),
                ],
            ),
            Device(
                id="DIST-SW-01",
                hostname="DIST-SW-01",
                mgmt_ip="10.0.1.1",
                platform="C9300-24T",
                serial="FCW2301B001",
                os_version="17.3.5",
                uptime="30 days, 12 hours, 5 minutes",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="GigabitEthernet1/0/1", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/2", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/24", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                ],
                vlans=[
                    VlanInfo(vlan_id="10", name="Data", status="active"),
                    VlanInfo(vlan_id="20", name="Voice", status="active"),
                    VlanInfo(vlan_id="100", name="Management", status="active"),
                ],
                etherchannels=[
                    EtherChannelInfo(
                        channel_id="1",
                        port_channel="Po1",
                        layer="Layer2",
                        status="up",
                        protocol="LACP",
                        members=[
                            ChannelMember(
                                interface="GigabitEthernet1/0/1", status="P", status_desc="bundled"
                            ),  # noqa: E501
                            ChannelMember(
                                interface="GigabitEthernet1/0/2", status="P", status_desc="bundled"
                            ),  # noqa: E501
                        ],
                    ),
                ],
                stp_info=[
                    STPVlanInfo(
                        vlan_id="1",
                        protocol="rstp",
                        root_priority="32769",
                        root_address="0cd5.d366.2400",
                        root_cost="4",
                        is_root=False,
                        bridge_priority="32770",
                        bridge_address="aabb.cc01.0100",
                        ports=[
                            STPPortInfo(
                                interface="GigabitEthernet1/0/24",
                                role="Root",
                                state="FWD",
                                cost="4",
                                port_priority="128.24",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/1",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.1",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/2",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.2",
                                link_type="P2p",
                            ),  # noqa: E501
                        ],
                    ),
                    STPVlanInfo(
                        vlan_id="10",
                        protocol="rstp",
                        root_priority="24586",
                        root_address="0cd5.d366.2400",
                        root_cost="4",
                        is_root=False,
                        bridge_priority="32778",
                        bridge_address="aabb.cc01.0100",
                        ports=[
                            STPPortInfo(
                                interface="GigabitEthernet1/0/24",
                                role="Root",
                                state="FWD",
                                cost="4",
                                port_priority="128.24",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/1",
                                role="Desg",
                                state="FWD",
                                cost="4",
                                port_priority="128.1",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/2",
                                role="Altn",
                                state="BLK",
                                cost="4",
                                port_priority="128.2",
                                link_type="P2p",
                            ),  # noqa: E501
                        ],
                    ),
                ],
            ),
            Device(
                id="DIST-SW-02",
                hostname="DIST-SW-02",
                mgmt_ip="10.0.1.2",
                platform="C9300-24T",
                serial="FCW2301B002",
                os_version="17.3.5",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="GigabitEthernet1/0/1", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/2", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/24", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                ],
                vlans=[
                    VlanInfo(vlan_id="10", name="Data", status="active"),
                    VlanInfo(vlan_id="20", name="Voice", status="active"),
                    VlanInfo(vlan_id="100", name="Management", status="active"),
                ],
                stp_info=[
                    STPVlanInfo(
                        vlan_id="1",
                        protocol="rstp",
                        root_priority="32769",
                        root_address="0cd5.d366.2400",
                        root_cost="4",
                        is_root=False,
                        bridge_priority="32771",
                        bridge_address="aabb.cc02.0200",
                        ports=[
                            STPPortInfo(
                                interface="GigabitEthernet1/0/24",
                                role="Root",
                                state="FWD",
                                cost="4",
                                port_priority="128.24",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/1",
                                role="Altn",
                                state="BLK",
                                cost="4",
                                port_priority="128.1",
                                link_type="P2p",
                            ),  # noqa: E501
                        ],
                    ),
                    STPVlanInfo(
                        vlan_id="10",
                        protocol="rstp",
                        root_priority="24586",
                        root_address="0cd5.d366.2400",
                        root_cost="4",
                        is_root=False,
                        bridge_priority="32778",
                        bridge_address="aabb.cc02.0200",
                        ports=[
                            STPPortInfo(
                                interface="GigabitEthernet1/0/24",
                                role="Root",
                                state="FWD",
                                cost="4",
                                port_priority="128.24",
                                link_type="P2p",
                            ),  # noqa: E501
                            STPPortInfo(
                                interface="GigabitEthernet1/0/1",
                                role="Altn",
                                state="BLK",
                                cost="4",
                                port_priority="128.1",
                                link_type="P2p",
                            ),  # noqa: E501
                        ],
                    ),
                ],
            ),
            Device(
                id="ACCESS-SW-01",
                hostname="ACCESS-SW-01",
                mgmt_ip="10.0.2.1",
                platform="C9200L-48PXG-4X",
                serial="FCW2302C001",
                os_version="17.6.3",
                uptime="10 weeks, 2 days, 7 hours",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="GigabitEthernet1/0/1", status="connected", vlan="10", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/2", status="connected", vlan="10", speed="100"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/3", status="notconnect", vlan="10", speed="auto"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/48", status="connected", vlan="30", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/1/1", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                ],
                vlans=[
                    VlanInfo(vlan_id="10", name="Data", status="active"),
                    VlanInfo(vlan_id="20", name="Voice", status="active"),
                    VlanInfo(vlan_id="30", name="Wireless", status="active"),
                ],
            ),
            Device(
                id="ACCESS-SW-02",
                hostname="ACCESS-SW-02",
                mgmt_ip="10.0.2.2",
                platform="C9200L-24PXG-4X",
                serial="FCW2302C002",
                os_version="17.6.3",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="GigabitEthernet1/0/1", status="connected", vlan="10", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/2", status="notconnect", vlan="10", speed="auto"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet1/0/24", status="connected", vlan="trunk", speed="1G"
                    ),  # noqa: E501
                ],
                vlans=[
                    VlanInfo(vlan_id="10", name="Data", status="active"),
                    VlanInfo(vlan_id="20", name="Voice", status="active"),
                ],
            ),
            Device(
                id="ACCESS-SW-03",
                hostname="ACCESS-SW-03",
                mgmt_ip="10.0.2.3",
                platform="C9200L-48P-4G",
                serial="FCW2302C003",
                os_version=None,
                status=DeviceStatus.TIMEOUT,
                interfaces=[],
                vlans=[],
            ),
            Device(
                id="ROUTER-01",
                hostname="ROUTER-01",
                mgmt_ip="10.0.0.254",
                platform="ISR4331/K9",
                serial="FGL2210A001",
                os_version="16.12.7",
                uptime="120 days, 8 hours, 15 minutes",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="GigabitEthernet0/0/0", status="connected", vlan="—", speed="1G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="GigabitEthernet0/0/1", status="connected", vlan="—", speed="1G"
                    ),  # noqa: E501
                ],
                vlans=[],
            ),
            Device(
                id="AP-FLOOR-1A",
                hostname="AP-FLOOR-1A",
                mgmt_ip="10.0.3.1",
                platform="AIR-AP2802I-B-K9",
                serial=None,
                os_version=None,
                status=DeviceStatus.PLACEHOLDER,
                interfaces=[],
                vlans=[],
            ),
            Device(
                id="AP-FLOOR-2B",
                hostname="AP-FLOOR-2B",
                mgmt_ip="10.0.3.2",
                platform="C9115AXI-B",
                serial=None,
                os_version=None,
                status=DeviceStatus.PLACEHOLDER,
                interfaces=[],
                vlans=[],
            ),
            Device(
                id="NXOS-SPINE-01",
                hostname="NXOS-SPINE-01",
                mgmt_ip="10.0.10.1",
                platform="Nexus9000 C93180YC-FX3",
                serial="FDO23456789",
                os_version="10.3(1)",
                uptime="120 days, 3 hours, 22 minutes",
                status=DeviceStatus.OK,
                interfaces=[
                    InterfaceInfo(
                        name="Ethernet1/1", status="connected", vlan="trunk", speed="100G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="Ethernet1/2", status="connected", vlan="trunk", speed="100G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="Ethernet1/3", status="connected", vlan="trunk", speed="100G"
                    ),  # noqa: E501
                    InterfaceInfo(
                        name="Ethernet1/49", status="connected", vlan="trunk", speed="100G"
                    ),  # noqa: E501
                    InterfaceInfo(name="loopback0", status="connected", ip_address="10.0.10.1"),
                    InterfaceInfo(name="nve1", status="connected", ip_address="10.0.10.1"),
                ],
                vlans=[
                    VlanInfo(vlan_id="1", name="default", status="active"),
                    VlanInfo(vlan_id="1001", name="VXLAN-Prod", status="active"),
                    VlanInfo(vlan_id="1002", name="VXLAN-Dev", status="active"),
                ],
                route_table=[
                    RouteEntry(
                        protocol="C",
                        route_type="connected",
                        destination="10.0.10.0/24",
                        interface="loopback0",
                    ),  # noqa: E501
                    RouteEntry(
                        protocol="B",
                        route_type="bgp",
                        destination="10.1.1.0/24",
                        next_hop="10.0.10.2",
                        metric="20/0",
                    ),  # noqa: E501
                    RouteEntry(
                        protocol="B",
                        route_type="bgp",
                        destination="10.1.2.0/24",
                        next_hop="10.0.10.3",
                        metric="20/0",
                    ),  # noqa: E501
                ],
                nve_peers=[
                    NVEPeer(
                        interface="nve1",
                        peer_ip="10.1.1.2",
                        state="Up",
                        learn_type="CP",
                        uptime="1d02h",
                        router_mac="5254.0012.3456",
                    ),  # noqa: E501
                    NVEPeer(
                        interface="nve1",
                        peer_ip="10.1.1.3",
                        state="Up",
                        learn_type="CP",
                        uptime="2d05h",
                        router_mac="5254.0012.3457",
                    ),  # noqa: E501
                    NVEPeer(
                        interface="nve1",
                        peer_ip="10.1.1.4",
                        state="Down",
                        learn_type="CP",
                        uptime="00:00:00",
                        router_mac="n/a",
                    ),  # noqa: E501
                ],
                vni_mappings=[
                    VNIMapping(
                        interface="nve1",
                        vni="50001",
                        multicast_group="UnicastBGP",
                        state="Up",
                        mode="CP",
                        vni_type="L2 [1001]",
                        bd_vrf="1001",
                    ),  # noqa: E501
                    VNIMapping(
                        interface="nve1",
                        vni="50002",
                        multicast_group="UnicastBGP",
                        state="Up",
                        mode="CP",
                        vni_type="L2 [1002]",
                        bd_vrf="1002",
                    ),  # noqa: E501
                    VNIMapping(
                        interface="nve1",
                        vni="50003",
                        multicast_group="239.1.1.1",
                        state="Up",
                        mode="CP",
                        vni_type="L2 [1003]",
                        bd_vrf="1003",
                    ),  # noqa: E501
                    VNIMapping(
                        interface="nve1",
                        vni="50100",
                        multicast_group="n/a",
                        state="Up",
                        mode="CP",
                        vni_type="L3 [Tenant-VRF]",
                        bd_vrf="Tenant-VRF",
                    ),  # noqa: E501
                ],
                evpn_neighbors=[
                    EVPNNeighbor(
                        neighbor="10.1.1.2",
                        asn="65001",
                        version="4",
                        msg_rcvd="12345",
                        msg_sent="12300",
                        up_down="1d02h",
                        state_pfx_rcv="100",
                    ),  # noqa: E501
                    EVPNNeighbor(
                        neighbor="10.1.1.3",
                        asn="65001",
                        version="4",
                        msg_rcvd="9876",
                        msg_sent="9800",
                        up_down="2d05h",
                        state_pfx_rcv="85",
                    ),  # noqa: E501
                ],
            ),
        ],
        links=[
            Link(
                source="ROUTER-01",
                target="CORE-SW-01",
                source_intf="GigabitEthernet0/0/0",
                target_intf="TenGigabitEthernet1/1/1",
                protocol="CDP",
            ),  # noqa: E501
            Link(
                source="CORE-SW-01",
                target="DIST-SW-01",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet1/0/24",
                protocol="CDP",
            ),  # noqa: E501
            Link(
                source="CORE-SW-01",
                target="DIST-SW-02",
                source_intf="GigabitEthernet1/0/2",
                target_intf="GigabitEthernet1/0/24",
                protocol="CDP",
            ),  # noqa: E501
            Link(
                source="DIST-SW-01",
                target="ACCESS-SW-01",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet1/1/1",
                protocol="CDP",
            ),  # noqa: E501
            Link(
                source="DIST-SW-01",
                target="ACCESS-SW-02",
                source_intf="GigabitEthernet1/0/2",
                target_intf="GigabitEthernet1/0/24",
                protocol="CDP",
            ),  # noqa: E501
            Link(
                source="DIST-SW-02",
                target="ACCESS-SW-03",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet1/1/1",
                protocol="CDP",
            ),  # noqa: E501
            Link(
                source="ACCESS-SW-01",
                target="AP-FLOOR-1A",
                source_intf="GigabitEthernet1/0/48",
                target_intf="GigabitEthernet0",
                protocol="CDP",
            ),  # noqa: E501
            Link(
                source="ACCESS-SW-02",
                target="AP-FLOOR-2B",
                source_intf="GigabitEthernet1/0/1",
                target_intf="GigabitEthernet0",
                protocol="LLDP",
            ),  # noqa: E501
            Link(
                source="CORE-SW-01",
                target="NXOS-SPINE-01",
                source_intf="GigabitEthernet1/0/3",
                target_intf="Ethernet1/49",
                protocol="CDP",
            ),  # noqa: E501
        ],
        failures=[
            Failure(
                target="10.0.2.3",
                reason="timeout",
                detail="Connection timed out after 30s — ACCESS-SW-03",
            ),  # noqa: E501
            Failure(target="10.0.4.1", reason="unreachable", detail="No route to host"),
            Failure(
                target="10.0.4.2",
                reason="auth_failed",
                detail="Authentication failed — bad credentials",
            ),  # noqa: E501
        ],
    )
    await _store_module.store.save(result)
    return result
