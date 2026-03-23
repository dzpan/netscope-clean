"""Full-text search over collected network data using SQLite FTS5.

When SQLite is available (NETSCOPE_DB_PATH set), all discovered data is
indexed into an FTS5 virtual table and queries are ranked by relevance.

When running without SQLite (in-memory mode), a linear scan over the current
session is used as a fallback — same result shape, no persistence.
"""

from __future__ import annotations

import re
import sqlite3
from typing import TYPE_CHECKING

from backend.models import SearchHit, SearchResponse, TopologyResult

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# MAC address helpers
# ---------------------------------------------------------------------------

_MAC_STRIP_RE = re.compile(r"[:\-.]")


def _normalize_mac(mac: str) -> str:
    """Strip delimiters and lowercase — canonical 12-char hex form."""
    return _MAC_STRIP_RE.sub("", mac).lower()


def _mac_variants(mac: str) -> str:
    """Return space-joined string with three MAC formats for FTS indexing."""
    raw = _normalize_mac(mac)
    if len(raw) != 12:
        return mac  # not a valid MAC, return as-is
    colon = ":".join(raw[i : i + 2] for i in range(0, 12, 2))
    cisco = ".".join(raw[i : i + 4] for i in range(0, 12, 4))
    dash = "-".join(raw[i : i + 2] for i in range(0, 12, 2))
    return f"{raw} {colon} {cisco} {dash}"


# ---------------------------------------------------------------------------
# FTS5 DDL (injected into store_sqlite._DDL)
# ---------------------------------------------------------------------------

SEARCH_FTS_DDL = """\
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    label,
    detail,
    session_id UNINDEXED,
    device_id  UNINDEXED,
    result_type UNINDEXED,
    tab         UNINDEXED
);
"""

# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------


def _rows_for_result(result: TopologyResult) -> list[tuple[str, str, str, str, str, str]]:
    """Convert a TopologyResult into (label, detail, session_id, device_id, type, tab) rows."""
    rows: list[tuple[str, str, str, str, str, str]] = []
    sid = result.session_id

    for dev in result.devices:
        # ----- device -----
        hostname = dev.hostname or ""
        detail_parts = [dev.mgmt_ip]
        if dev.platform:
            detail_parts.append(dev.platform)
        if dev.os_version:
            detail_parts.append(dev.os_version)
        if dev.serial:
            detail_parts.append(dev.serial)
        rows.append(
            (
                f"{hostname} {dev.mgmt_ip}".strip(),
                " ".join(detail_parts),
                sid,
                dev.id,
                "device",
                "overview",
            )
        )

        prefix = hostname or dev.mgmt_ip

        # ----- interfaces -----
        for intf in dev.interfaces:
            intf_detail_parts: list[str] = []
            if intf.description:
                intf_detail_parts.append(intf.description)
            if intf.ip_address:
                intf_detail_parts.append(intf.ip_address)
            if intf.vlan:
                intf_detail_parts.append(f"vlan{intf.vlan}")
            if intf.status:
                intf_detail_parts.append(intf.status)
            rows.append(
                (
                    f"{prefix} {intf.name}",
                    " ".join(intf_detail_parts),
                    sid,
                    dev.id,
                    "interface",
                    "interfaces",
                )
            )

        # ----- VLANs -----
        for vlan in dev.vlans:
            name_part = vlan.name or ""
            rows.append(
                (
                    f"vlan{vlan.vlan_id} {name_part}".strip(),
                    prefix,
                    sid,
                    dev.id,
                    "vlan",
                    "vlans",
                )
            )

        # ----- ARP table -----
        for arp in dev.arp_table:
            rows.append(
                (
                    arp.ip_address,
                    f"{_mac_variants(arp.mac_address)} {arp.interface}",
                    sid,
                    dev.id,
                    "ip",
                    "arp",
                )
            )

        # ----- MAC table -----
        for mac_entry in dev.mac_table:
            vlan_part = f"vlan{mac_entry.vlan_id}" if mac_entry.vlan_id else ""
            rows.append(
                (
                    _mac_variants(mac_entry.mac_address),
                    f"{vlan_part} {mac_entry.interface}".strip(),
                    sid,
                    dev.id,
                    "mac",
                    "mac",
                )
            )

        # ----- LLDP capabilities -----
        if dev.capabilities:
            caps_str = " ".join(dev.capabilities)
            rows.append(
                (
                    f"{prefix} {caps_str}",
                    f"LLDP capabilities: {', '.join(dev.capabilities)}",
                    sid,
                    dev.id,
                    "lldp",
                    "overview",
                )
            )

        # ----- Route table -----
        for route in dev.route_table:
            detail_r: list[str] = []
            if route.next_hop:
                detail_r.append(route.next_hop)
            if route.interface:
                detail_r.append(route.interface)
            if route.route_type:
                detail_r.append(route.route_type)
            rows.append(
                (
                    route.destination,
                    " ".join(detail_r),
                    sid,
                    dev.id,
                    "route",
                    "routes",
                )
            )

    return rows


def build_search_index(conn: sqlite3.Connection, result: TopologyResult) -> None:
    """Rebuild the FTS5 index entries for a session (delete old + insert new)."""
    rows = _rows_for_result(result)
    conn.execute("DELETE FROM search_index WHERE session_id = ?", (result.session_id,))
    conn.executemany(
        "INSERT INTO search_index(label, detail, session_id, device_id, result_type, tab)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

_PUNC_RE = re.compile(r"[^\w\s]")


def _fts_query(term: str) -> str:
    """Build an FTS5 query from a user search term.

    - Strips punctuation (but keeps alphanumerics) so users can type IPs/MACs
      in any delimiter style.
    - Appends `*` to each token for prefix matching.
    """
    tokens = _PUNC_RE.sub(" ", term).split()
    if not tokens:
        return '""'
    return " ".join(f"{t}*" for t in tokens)


def search_index(
    conn: sqlite3.Connection,
    q: str,
    session_id: str | None = None,
    limit: int = 50,
) -> SearchResponse:
    """Query the FTS5 index and return ranked, grouped results."""
    if not q.strip():
        return SearchResponse(query=q, total=0, results=[])

    fts_q = _fts_query(q)
    base_sql = (
        "SELECT label, detail, session_id, device_id, result_type, tab, rank"
        " FROM search_index WHERE search_index MATCH ?"
    )
    params: list[object] = [fts_q]

    if session_id:
        base_sql += " AND session_id = ?"
        params.append(session_id)

    base_sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    try:
        rows = conn.execute(base_sql, params).fetchall()
    except sqlite3.OperationalError:
        # Malformed query or FTS error — return empty
        return SearchResponse(query=q, total=0, results=[])

    hits = [
        SearchHit(
            label=row[0],
            detail=row[1] or None,
            session_id=row[2],
            device_id=row[3],
            result_type=row[4],
            tab=row[5],
            score=float(-row[6]),  # rank is negative; negate for ascending "score"
        )
        for row in rows
    ]
    return SearchResponse(query=q, total=len(hits), results=hits)


# ---------------------------------------------------------------------------
# In-memory fallback (no SQLite)
# ---------------------------------------------------------------------------


def _text_matches(q_lower: str, *fields: str | None) -> bool:
    return any(q_lower in (f or "").lower() for f in fields)


def search_in_memory(
    sessions: list[TopologyResult],
    q: str,
    session_id: str | None = None,
    limit: int = 50,
) -> SearchResponse:
    """Simple substring search over in-memory sessions (no ranking)."""
    if not q.strip():
        return SearchResponse(query=q, total=0, results=[])

    q_lower = q.lower()
    hits: list[SearchHit] = []

    for result in sessions:
        if session_id and result.session_id != session_id:
            continue
        sid = result.session_id

        for dev in result.devices:
            hostname = dev.hostname or ""
            if _text_matches(q_lower, hostname, dev.mgmt_ip, dev.platform, dev.serial):
                hits.append(
                    SearchHit(
                        label=f"{hostname} {dev.mgmt_ip}".strip(),
                        detail=dev.platform,
                        session_id=sid,
                        device_id=dev.id,
                        result_type="device",
                        tab="overview",
                    )
                )
            for intf in dev.interfaces:
                if _text_matches(q_lower, intf.name, intf.ip_address, intf.description):
                    hits.append(
                        SearchHit(
                            label=f"{hostname or dev.mgmt_ip} {intf.name}",
                            detail=intf.ip_address or intf.description,
                            session_id=sid,
                            device_id=dev.id,
                            result_type="interface",
                            tab="interfaces",
                        )
                    )
            for arp in dev.arp_table:
                norm_mac = _normalize_mac(arp.mac_address)
                norm_q = _normalize_mac(q_lower) if len(q_lower) >= 4 else q_lower
                if _text_matches(q_lower, arp.ip_address) or norm_q in norm_mac:
                    hits.append(
                        SearchHit(
                            label=arp.ip_address,
                            detail=arp.mac_address,
                            session_id=sid,
                            device_id=dev.id,
                            result_type="ip",
                            tab="arp",
                        )
                    )
            for mac_entry in dev.mac_table:
                norm_mac = _normalize_mac(mac_entry.mac_address)
                norm_q = _normalize_mac(q_lower) if len(q_lower) >= 4 else q_lower
                if norm_q in norm_mac:
                    hits.append(
                        SearchHit(
                            label=mac_entry.mac_address,
                            detail=mac_entry.interface,
                            session_id=sid,
                            device_id=dev.id,
                            result_type="mac",
                            tab="mac",
                        )
                    )
            if dev.capabilities and _text_matches(q_lower, *dev.capabilities):
                hits.append(
                    SearchHit(
                        label=f"{hostname or dev.mgmt_ip} {' '.join(dev.capabilities)}",
                        detail=f"LLDP capabilities: {', '.join(dev.capabilities)}",
                        session_id=sid,
                        device_id=dev.id,
                        result_type="lldp",
                        tab="overview",
                    )
                )
            for vlan in dev.vlans:
                if _text_matches(q_lower, vlan.vlan_id, vlan.name):
                    hits.append(
                        SearchHit(
                            label=f"VLAN {vlan.vlan_id} {vlan.name or ''}".strip(),
                            detail=hostname,
                            session_id=sid,
                            device_id=dev.id,
                            result_type="vlan",
                            tab="vlans",
                        )
                    )
            for route in dev.route_table:
                if _text_matches(q_lower, route.destination, route.next_hop):
                    hits.append(
                        SearchHit(
                            label=route.destination,
                            detail=route.next_hop,
                            session_id=sid,
                            device_id=dev.id,
                            result_type="route",
                            tab="routes",
                        )
                    )

        if len(hits) >= limit:
            break

    hits = hits[:limit]
    return SearchResponse(query=q, total=len(hits), results=hits)
