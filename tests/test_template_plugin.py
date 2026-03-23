"""Tests for the YAML template-driven vendor plugin."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.vendors.template import TemplatePlugin, load_templates_from_dir

EXAMPLE_TEMPLATE = """\
vendor_id: testvendor
display_name: Test Vendor Switch
detect_pattern: "TestOS"
on_open_commands:
  - "no page"
version_parsing:
  hostname_pattern: "Hostname:\\\\s+(\\\\S+)"
  platform_pattern: "Model:\\\\s+(.+?)\\\\s*$"
  os_version_pattern: "Version:\\\\s+(\\\\S+)"
neighbor_commands:
  lldp: "show lldp remote"
not_enabled_markers:
  lldp:
    - "LLDP disabled"
commands:
  interfaces:
    - command: "show interfaces"
      parser: tabular
      header_pattern: "Port\\\\s+Status"
      columns:
        - { header: "Port", field: "name" }
        - { header: "Status", field: "status" }
        - { header: "Speed", field: "speed" }
  vlans:
    - command: "show vlans"
      parser: regex
      pattern: "(?P<vlan_id>\\\\d+)\\\\s+(?P<name>\\\\S+)\\\\s+(?P<status>\\\\S+)"
"""

VERSION_OUTPUT = """\
TestOS Switch Software
Hostname: test-sw-01
Model: TS-2400-48P
Version: 2.5.1
Uptime: 10 days
"""

INTERFACES_OUTPUT = """\
Port       Status     Speed
1          up         1G
2          down       1G
3          up         10G
"""

VLANS_OUTPUT = """\
VLAN List:
10 Production active
20 Management active
99 Quarantine suspended
"""


@pytest.fixture
def template_path(tmp_path: Path) -> Path:
    p = tmp_path / "testvendor.yaml"
    p.write_text(EXAMPLE_TEMPLATE)
    return p


@pytest.fixture
def plugin(template_path: Path) -> TemplatePlugin:
    return TemplatePlugin(template_path)


class TestTemplatePlugin:
    def test_vendor_id(self, plugin: TemplatePlugin) -> None:
        assert plugin.vendor_id == "testvendor"
        assert plugin.display_name == "Test Vendor Switch"

    def test_detect(self, plugin: TemplatePlugin) -> None:
        assert plugin.detect("TestOS version 2.5")
        assert not plugin.detect("Cisco IOS Software")

    def test_parse_version(self, plugin: TemplatePlugin) -> None:
        ver = plugin.parse_version(VERSION_OUTPUT)
        assert ver.hostname == "test-sw-01"
        assert ver.platform == "TS-2400-48P"
        assert ver.os_version == "2.5.1"

    def test_get_commands(self, plugin: TemplatePlugin) -> None:
        cmds = plugin.get_commands(frozenset(["interfaces", "vlans"]))
        assert "interfaces" in cmds
        assert "show interfaces" in cmds["interfaces"]
        assert "vlans" in cmds
        assert "show vlans" in cmds["vlans"]

    def test_get_commands_ignores_unknown(self, plugin: TemplatePlugin) -> None:
        cmds = plugin.get_commands(frozenset(["bogus"]))
        assert cmds == {}

    def test_parse_tabular_interfaces(self, plugin: TemplatePlugin) -> None:
        result = plugin.parse_group("interfaces", {"show interfaces": INTERFACES_OUTPUT})
        intfs = result["interfaces"]
        assert len(intfs) == 3
        assert intfs[0].name == "1"
        assert intfs[0].status == "up"
        assert intfs[0].speed == "1G"
        assert intfs[1].status == "down"

    def test_parse_regex_vlans(self, plugin: TemplatePlugin) -> None:
        result = plugin.parse_group("vlans", {"show vlans": VLANS_OUTPUT})
        vlans = result["vlans"]
        assert len(vlans) == 3
        assert vlans[0].vlan_id == "10"
        assert vlans[0].name == "Production"
        assert vlans[2].vlan_id == "99"

    def test_parse_empty_output(self, plugin: TemplatePlugin) -> None:
        result = plugin.parse_group("interfaces", {})
        assert result == {}

    def test_parse_unknown_group(self, plugin: TemplatePlugin) -> None:
        result = plugin.parse_group("nonexistent", {})
        assert result == {}

    def test_neighbor_commands(self, plugin: TemplatePlugin) -> None:
        cmds = plugin.neighbor_commands()
        assert cmds["lldp"] == "show lldp remote"

    def test_not_enabled_markers(self, plugin: TemplatePlugin) -> None:
        markers = plugin.not_enabled_markers()
        assert "LLDP disabled" in markers["lldp"]

    def test_driver_kwargs_default(self, plugin: TemplatePlugin) -> None:
        assert plugin.get_driver_kwargs() == {}


class TestLoadTemplatesFromDir:
    def test_loads_yaml_files(self, tmp_path: Path) -> None:
        (tmp_path / "vendor1.yaml").write_text('vendor_id: v1\ndetect_pattern: "V1"\ncommands: {}')
        (tmp_path / "vendor2.yaml").write_text('vendor_id: v2\ndetect_pattern: "V2"\ncommands: {}')
        (tmp_path / "readme.txt").write_text("not a template")

        plugins = load_templates_from_dir(tmp_path)
        assert len(plugins) == 2
        ids = {p.vendor_id for p in plugins}
        assert ids == {"v1", "v2"}

    def test_empty_dir(self, tmp_path: Path) -> None:
        plugins = load_templates_from_dir(tmp_path)
        assert plugins == []

    def test_nonexistent_dir(self) -> None:
        plugins = load_templates_from_dir("/nonexistent/path")
        assert plugins == []

    def test_skips_invalid_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "good.yaml").write_text('vendor_id: good\ndetect_pattern: "Good"\ncommands: {}')
        (tmp_path / "bad.yaml").write_text("this is not: valid: yaml: [[[")

        plugins = load_templates_from_dir(tmp_path)
        # Should load the good one and skip the bad one
        assert len(plugins) >= 1
        assert any(p.vendor_id == "good" for p in plugins)
