"""Multi-vendor parser plugin framework.

Each vendor provides a plugin class implementing the ``VendorPlugin`` protocol.
The ``VendorRegistry`` singleton auto-detects the correct plugin for a device
based on ``show version`` output.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from backend.models import NeighborRecord, VersionInfo


@runtime_checkable
class VendorPlugin(Protocol):
    """Interface that every vendor parser plugin must satisfy."""

    vendor_id: str  # "cisco", "arista", "juniper", "hpe"
    display_name: str  # "Cisco IOS-XE / NX-OS"

    def detect(self, version_output: str) -> bool:
        """Return True if this plugin handles the device."""
        ...

    def parse_version(self, output: str) -> VersionInfo:
        """Parse ``show version`` (or equivalent) output."""
        ...

    def parse_neighbors(
        self,
        cdp_output: str | None,
        lldp_output: str | None,
        platform: str | None = None,
    ) -> list[NeighborRecord]:
        """Parse CDP and/or LLDP neighbor output into records."""
        ...

    def get_commands(self, groups: frozenset[str]) -> dict[str, list[str]]:
        """Return ``{group_name: [show commands]}`` for active collection groups."""
        ...

    def parse_group(self, group: str, outputs: dict[str, str]) -> dict[str, Any]:
        """Parse the raw outputs for a single collection group.

        Returns a dict whose keys match ``Device`` field names, e.g.::

            {"interfaces": [...], "vlans": [...]}
        """
        ...

    async def on_open(self, conn: Any) -> None:
        """Per-vendor terminal setup (pagination, modes) after connection open."""
        ...

    def get_driver_kwargs(self) -> dict[str, Any]:
        """Extra Scrapli driver keyword args (e.g. different driver class)."""
        ...

    def neighbor_commands(self) -> dict[str, str]:
        """Return ``{"cdp": "<cmd>", "lldp": "<cmd>"}`` for neighbor discovery.

        A vendor may omit a key if that protocol is not supported.
        """
        ...

    def not_enabled_markers(self) -> dict[str, list[str]]:
        """Return ``{"cdp": [...], "lldp": [...]}`` — strings that indicate the
        protocol is not enabled on this device."""
        ...


class VendorRegistry:
    """Ordered collection of vendor plugins with detection-based lookup."""

    def __init__(self) -> None:
        self._plugins: list[VendorPlugin] = []
        self._by_id: dict[str, VendorPlugin] = {}

    def register(self, plugin: VendorPlugin, *, priority: int = 100) -> None:
        """Register a plugin.  Lower ``priority`` = matched first."""
        object.__setattr__(plugin, "_priority", priority)
        self._plugins.append(plugin)
        self._plugins.sort(key=lambda p: getattr(p, "_priority", 100))
        self._by_id[plugin.vendor_id] = plugin

    def detect(self, version_output: str) -> VendorPlugin | None:
        """Return the first plugin whose ``detect()`` returns True."""
        for plugin in self._plugins:
            if plugin.detect(version_output):
                return plugin
        return None

    def get(self, vendor_id: str) -> VendorPlugin | None:
        """Lookup a plugin by vendor ID."""
        return self._by_id.get(vendor_id)

    def all_plugins(self) -> list[VendorPlugin]:
        """Return all registered plugins in priority order."""
        return list(self._plugins)


# Module-level singleton — populated by vendor modules at import time.
registry = VendorRegistry()
