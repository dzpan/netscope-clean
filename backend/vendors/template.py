"""YAML-driven vendor plugin for community-contributable device support.

A ``TemplatePlugin`` reads a YAML definition file and exposes the same
``VendorPlugin`` interface, using configurable regex/tabular parsers for
each command group.  This lets users add support for new vendors without
writing Python code.

Template format::

    vendor_id: extreme
    display_name: Extreme Networks EXOS
    detect_pattern: "ExtremeXOS"
    on_open_commands:
      - "disable clipaging"
    neighbor_commands:
      lldp: "show lldp neighbors detail"
    not_enabled_markers:
      lldp:
        - "LLDP is not enabled"
    commands:
      interfaces:
        - command: "show ports information"
          parser: tabular
          header_pattern: "Port\\s+Display"
          columns:
            - { header: "Port", field: "name" }
            - { header: "Display String", field: "description" }
            - { header: "Status", field: "status" }
      vlans:
        - command: "show vlan"
          parser: regex
          pattern: "(?P<vlan_id>\\d+)\\s+(?P<name>\\S+)\\s+(?P<status>\\S+)"
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from backend.models import (
    InterfaceInfo,
    NeighborRecord,
    VersionInfo,
    VlanInfo,
)
from backend.parsers import parse_lldp_neighbors


class TemplatePlugin:
    """Vendor plugin driven by a YAML template file."""

    def __init__(self, template_path: str | Path) -> None:
        path = Path(template_path)
        with path.open() as f:
            self._cfg: dict[str, Any] = yaml.safe_load(f)

        self.vendor_id: str = self._cfg["vendor_id"]
        self.display_name: str = self._cfg.get("display_name", self.vendor_id)
        self._detect_re = re.compile(self._cfg["detect_pattern"], re.IGNORECASE)
        self._on_open: list[str] = self._cfg.get("on_open_commands", [])
        self._commands: dict[str, list[dict[str, Any]]] = self._cfg.get("commands", {})
        self._neighbor_cmds: dict[str, str] = self._cfg.get("neighbor_commands", {})
        self._not_enabled: dict[str, list[str]] = self._cfg.get("not_enabled_markers", {})

    # --- detection -----------------------------------------------------------

    def detect(self, version_output: str) -> bool:
        return bool(self._detect_re.search(version_output))

    # --- version -------------------------------------------------------------

    def parse_version(self, output: str) -> VersionInfo:
        """Best-effort version parsing using optional template patterns."""
        ver_cfg = self._cfg.get("version_parsing", {})
        hostname = _template_extract(ver_cfg.get("hostname_pattern"), output)
        platform = _template_extract(ver_cfg.get("platform_pattern"), output)
        serial = _template_extract(ver_cfg.get("serial_pattern"), output)
        os_version = _template_extract(ver_cfg.get("os_version_pattern"), output)
        uptime = _template_extract(ver_cfg.get("uptime_pattern"), output)
        base_mac = _template_extract(ver_cfg.get("base_mac_pattern"), output)
        return VersionInfo(
            hostname=hostname,
            platform=platform,
            serial=serial,
            os_version=os_version,
            uptime=uptime,
            base_mac=base_mac,
        )

    # --- neighbors -----------------------------------------------------------

    def parse_neighbors(
        self,
        cdp_output: str | None,
        lldp_output: str | None,
        platform: str | None = None,
    ) -> list[NeighborRecord]:
        """Use the standard LLDP parser — LLDP is vendor-agnostic."""
        records: list[NeighborRecord] = []
        if lldp_output:
            records.extend(parse_lldp_neighbors(lldp_output, platform=platform))
        return records

    # --- command mapping -----------------------------------------------------

    def get_commands(self, groups: frozenset[str]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for group in groups:
            if group in self._commands:
                result[group] = [entry["command"] for entry in self._commands[group]]
        return result

    # --- group parsing -------------------------------------------------------

    def parse_group(self, group: str, outputs: dict[str, str]) -> dict[str, Any]:
        if group not in self._commands:
            return {}

        all_items: list[Any] = []
        for entry in self._commands[group]:
            cmd = entry["command"]
            raw = outputs.get(cmd, "")
            if not raw:
                continue

            parser_type = entry.get("parser", "regex")
            if parser_type == "regex":
                all_items.extend(_parse_regex(entry, raw))
            elif parser_type == "tabular":
                all_items.extend(_parse_tabular(entry, raw))

        if not all_items:
            return {}
        return _build_group_result(group, all_items)

    # --- terminal setup ------------------------------------------------------

    async def on_open(self, conn: Any) -> None:
        for cmd in self._on_open:
            try:
                await conn.send_command(cmd)
            except Exception:
                pass

    # --- driver config -------------------------------------------------------

    def get_driver_kwargs(self) -> dict[str, Any]:
        return dict(self._cfg.get("driver_kwargs", {}))

    # --- neighbor commands ---------------------------------------------------

    def neighbor_commands(self) -> dict[str, str]:
        return dict(self._neighbor_cmds)

    def not_enabled_markers(self) -> dict[str, list[str]]:
        return dict(self._not_enabled)


# ---------------------------------------------------------------------------
# Template parsing helpers
# ---------------------------------------------------------------------------


def _template_extract(pattern: str | None, text: str) -> str | None:
    if not pattern:
        return None
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m and m.lastindex else None


def _parse_regex(entry: dict[str, Any], raw: str) -> list[dict[str, str]]:
    """Parse output using a named-group regex pattern."""
    pattern = entry.get("pattern", "")
    if not pattern:
        return []
    items: list[dict[str, str]] = []
    for m in re.finditer(pattern, raw, re.MULTILINE):
        items.append(m.groupdict())
    return items


def _parse_tabular(entry: dict[str, Any], raw: str) -> list[dict[str, str]]:
    """Parse output using column-position detection from a header line."""
    columns: list[dict[str, str]] = entry.get("columns", [])
    header_pattern = entry.get("header_pattern", "")
    if not columns or not header_pattern:
        return []

    items: list[dict[str, str]] = []
    col_positions: list[tuple[str, int, int]] = []
    header_found = False

    for line in raw.splitlines():
        if not header_found:
            if re.search(header_pattern, line, re.IGNORECASE):
                # Detect column positions from header
                for i, col in enumerate(columns):
                    start = line.find(col["header"])
                    if start < 0:
                        continue
                    # End is the start of next column, or line end
                    end = len(line)
                    if i + 1 < len(columns):
                        next_start = line.find(columns[i + 1]["header"])
                        if next_start > start:
                            end = next_start
                    col_positions.append((col["field"], start, end))
                header_found = True
            continue

        if re.match(r"^[\s-]*$", line):
            continue

        row: dict[str, str] = {}
        for field, start, end in col_positions:
            val = line[start:end].strip() if start < len(line) else ""
            if val:
                row[field] = val
        if row:
            items.append(row)

    return items


def _build_group_result(group: str, items: list[dict[str, str]]) -> dict[str, Any]:
    """Convert raw dicts into the appropriate model list for the group."""
    if group == "interfaces":
        return {
            "interfaces": [
                InterfaceInfo(
                    name=item.get("name", ""),
                    status=item.get("status"),
                    vlan=item.get("vlan"),
                    speed=item.get("speed"),
                    duplex=item.get("duplex"),
                    description=item.get("description"),
                )
                for item in items
                if item.get("name")
            ]
        }
    if group == "vlans":
        return {
            "vlans": [
                VlanInfo(
                    vlan_id=item.get("vlan_id", ""),
                    name=item.get("name"),
                    status=item.get("status"),
                )
                for item in items
                if item.get("vlan_id")
            ]
        }
    # Generic fallback: return raw dicts under the group name
    return {group: items}


def load_templates_from_dir(templates_dir: str | Path) -> list[TemplatePlugin]:
    """Load all YAML templates from a directory and return plugin instances."""
    path = Path(templates_dir)
    plugins: list[TemplatePlugin] = []
    if not path.is_dir():
        return plugins
    for yaml_file in sorted(path.glob("*.yaml")):
        try:
            plugins.append(TemplatePlugin(yaml_file))
        except Exception:
            continue
    return plugins
