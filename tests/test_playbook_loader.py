"""Tests for built-in playbook YAML template loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.playbook_loader import _parse_variable, load_builtin_playbooks
from backend.playbooks import VariableType

# ---------------------------------------------------------------------------
# _parse_variable tests
# ---------------------------------------------------------------------------


class TestParseVariable:
    def test_minimal_variable(self) -> None:
        raw = {"name": "interface"}
        var = _parse_variable(raw)
        assert var.name == "interface"
        assert var.var_type == VariableType.STRING
        assert var.required is True
        assert var.default is None

    def test_full_variable(self) -> None:
        raw = {
            "name": "vlan_id",
            "var_type": "int",
            "required": False,
            "default": "100",
            "description": "VLAN ID to assign",
            "choices": ["100", "200", "300"],
        }
        var = _parse_variable(raw)
        assert var.name == "vlan_id"
        assert var.var_type == VariableType.INT
        assert var.required is False
        assert var.default == "100"
        assert var.description == "VLAN ID to assign"
        assert var.choices == ["100", "200", "300"]

    def test_unknown_var_type_defaults_to_string(self) -> None:
        raw = {"name": "x", "var_type": "nonexistent_type"}
        var = _parse_variable(raw)
        assert var.var_type == VariableType.STRING

    def test_none_default_stays_none(self) -> None:
        raw = {"name": "x", "default": None}
        var = _parse_variable(raw)
        assert var.default is None


# ---------------------------------------------------------------------------
# load_builtin_playbooks tests
# ---------------------------------------------------------------------------


class TestLoadBuiltinPlaybooks:
    def test_loads_from_templates_dir(self) -> None:
        """Should load actual built-in templates if they exist."""
        playbooks = load_builtin_playbooks()
        # Should not crash; may or may not find templates
        assert isinstance(playbooks, list)
        for pb in playbooks:
            assert pb.builtin is True
            assert pb.id.startswith("builtin-")

    def test_missing_templates_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list if templates dir doesn't exist."""
        monkeypatch.setattr(
            "backend.playbook_loader._TEMPLATES_DIR",
            Path("/nonexistent/path"),
        )
        result = load_builtin_playbooks()
        assert result == []

    def test_loads_valid_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should parse a well-formed YAML template."""
        template = {
            "title": "Test Playbook",
            "description": "A test template",
            "category": "general",
            "platforms": ["iosxe"],
            "variables": [
                {"name": "interface", "required": True},
            ],
            "pre_checks": ["show ip int brief"],
            "steps": ["interface {{interface}}", "shutdown"],
            "post_checks": ["show ip int brief"],
            "rollback": ["interface {{interface}}", "no shutdown"],
        }
        yaml_file = tmp_path / "test-playbook.yaml"
        yaml_file.write_text(yaml.dump(template))

        monkeypatch.setattr("backend.playbook_loader._TEMPLATES_DIR", tmp_path)
        result = load_builtin_playbooks()
        assert len(result) == 1
        assert result[0].title == "Test Playbook"
        assert result[0].builtin is True
        assert result[0].id == "builtin-test-playbook"
        assert len(result[0].variables) == 1

    def test_skips_invalid_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should skip files with invalid YAML content."""
        (tmp_path / "bad.yaml").write_text("not: valid: yaml: {{{}}")
        (tmp_path / "good.yaml").write_text(yaml.dump({"title": "Good", "steps": ["show version"]}))
        monkeypatch.setattr("backend.playbook_loader._TEMPLATES_DIR", tmp_path)
        result = load_builtin_playbooks()
        # Should load the good one, skip the bad one
        assert any(pb.title == "Good" for pb in result)

    def test_skips_empty_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty YAML files should be skipped."""
        (tmp_path / "empty.yaml").write_text("")
        monkeypatch.setattr("backend.playbook_loader._TEMPLATES_DIR", tmp_path)
        result = load_builtin_playbooks()
        assert result == []

    def test_unknown_platform_defaults_to_iosxe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = {
            "title": "Platform Test",
            "platforms": ["unknown_platform"],
            "steps": ["show version"],
        }
        (tmp_path / "platform.yaml").write_text(yaml.dump(template))
        monkeypatch.setattr("backend.playbook_loader._TEMPLATES_DIR", tmp_path)
        result = load_builtin_playbooks()
        assert len(result) == 1
        from backend.playbooks import Platform

        assert result[0].platforms == [Platform.IOSXE]

    def test_unknown_category_defaults_to_general(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        template = {
            "title": "Category Test",
            "category": "nonexistent_category",
            "steps": ["show version"],
        }
        (tmp_path / "category.yaml").write_text(yaml.dump(template))
        monkeypatch.setattr("backend.playbook_loader._TEMPLATES_DIR", tmp_path)
        result = load_builtin_playbooks()
        assert len(result) == 1
        from backend.playbooks import PlaybookCategory

        assert result[0].category == PlaybookCategory.GENERAL
