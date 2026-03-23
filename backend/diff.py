"""Topology diff engine — compares two TopologyResult snapshots.

Computes added/removed devices, added/removed links, and field-level changes
on devices that exist in both snapshots.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from backend.models import (
    Device,
    DeviceChange,
    DeviceDiff,
    Link,
    LinkKey,
    TopologyDiff,
    TopologyResult,
)

# Device scalar fields to compare between snapshots.
_DEVICE_FIELDS: tuple[str, ...] = (
    "hostname",
    "platform",
    "serial",
    "os_version",
    "uptime",
    "status",
    "mgmt_ip",
)


def _link_key(link: Link) -> tuple[str, str, str, str | None]:
    """Canonical, order-independent key for a link (order-independent on endpoints)."""
    # Normalise None → empty string for comparison only
    a_cmp = (link.source, link.source_intf or "")
    b_cmp = (link.target, link.target_intf or "")
    if a_cmp <= b_cmp:
        return (link.source, link.target, link.source_intf, link.target_intf)
    return (link.target, link.source, link.target_intf or "", link.source_intf)


def _diff_device(prev: Device, curr: Device) -> DeviceDiff | None:
    """Return a DeviceDiff if any tracked fields changed, else None."""
    changes: list[DeviceChange] = []
    for field in _DEVICE_FIELDS:
        before = str(getattr(prev, field)) if getattr(prev, field) is not None else None
        after = str(getattr(curr, field)) if getattr(curr, field) is not None else None
        if before != after:
            changes.append(DeviceChange(field=field, before=before, after=after))
    if not changes:
        return None
    return DeviceDiff(
        device_id=curr.id,
        hostname=curr.hostname,
        changes=changes,
    )


def compute_diff(
    current: TopologyResult,
    previous: TopologyResult,
) -> TopologyDiff:
    """Compare *current* against *previous* and return a TopologyDiff.

    ``current`` is the newer snapshot; ``previous`` is the baseline.
    """
    prev_devices: dict[str, Device] = {d.id: d for d in previous.devices}
    curr_devices: dict[str, Device] = {d.id: d for d in current.devices}

    prev_ids = set(prev_devices)
    curr_ids = set(curr_devices)

    devices_added = sorted(curr_ids - prev_ids)
    devices_removed = sorted(prev_ids - curr_ids)

    devices_changed: list[DeviceDiff] = []
    for dev_id in prev_ids & curr_ids:
        diff = _diff_device(prev_devices[dev_id], curr_devices[dev_id])
        if diff is not None:
            devices_changed.append(diff)

    # Link diff (canonical, order-independent keys)
    prev_links: dict[tuple[str, str, str, str | None], Link] = {
        _link_key(lnk): lnk for lnk in previous.links
    }
    curr_links: dict[tuple[str, str, str, str | None], Link] = {
        _link_key(lnk): lnk for lnk in current.links
    }

    links_added = [
        LinkKey(
            source=lnk.source,
            target=lnk.target,
            source_intf=lnk.source_intf,
            target_intf=lnk.target_intf,
        )
        for key, lnk in curr_links.items()
        if key not in prev_links
    ]
    links_removed = [
        LinkKey(
            source=lnk.source,
            target=lnk.target,
            source_intf=lnk.source_intf,
            target_intf=lnk.target_intf,
        )
        for key, lnk in prev_links.items()
        if key not in curr_links
    ]

    total = (
        len(devices_added)
        + len(devices_removed)
        + len(devices_changed)
        + len(links_added)
        + len(links_removed)
    )

    return TopologyDiff(
        diff_id=str(uuid4()),
        current_session_id=current.session_id,
        previous_session_id=previous.session_id,
        computed_at=datetime.now(UTC),
        devices_added=devices_added,
        devices_removed=devices_removed,
        devices_changed=devices_changed,
        links_added=links_added,
        links_removed=links_removed,
        total_changes=total,
    )
