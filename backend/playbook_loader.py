"""Load built-in playbook templates from YAML files.

Scans ``backend/playbook_templates/*.yaml`` and converts each into a
:class:`Playbook` model with ``builtin=True``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from backend.playbooks import Platform, Playbook, PlaybookCategory, PlaybookVariable, VariableType

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "playbook_templates"


def _parse_variable(raw: dict[str, Any]) -> PlaybookVariable:
    """Parse a variable definition from YAML."""
    var_type_str = str(raw.get("var_type", "string"))
    try:
        var_type = VariableType(var_type_str)
    except ValueError:
        var_type = VariableType.STRING

    return PlaybookVariable(
        name=str(raw["name"]),
        var_type=var_type,
        required=bool(raw.get("required", True)),
        default=str(raw["default"]) if raw.get("default") is not None else None,
        description=str(raw.get("description", "")),
        choices=[str(c) for c in raw.get("choices", [])],
    )


def load_builtin_playbooks() -> list[Playbook]:
    """Load all YAML templates from the templates directory."""
    playbooks: list[Playbook] = []

    if not _TEMPLATES_DIR.exists():
        logger.warning("Playbook templates directory not found: %s", _TEMPLATES_DIR)
        return playbooks

    for yaml_file in sorted(_TEMPLATES_DIR.glob("*.yaml")):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data, dict):
                logger.warning("Skipping invalid template: %s", yaml_file.name)
                continue

            # Parse platforms
            platforms_raw = data.get("platforms", ["iosxe"])
            platforms: list[Platform] = []
            for p in platforms_raw:
                try:
                    platforms.append(Platform(str(p)))
                except ValueError:
                    pass
            if not platforms:
                platforms = [Platform.IOSXE]

            # Parse category
            try:
                category = PlaybookCategory(str(data.get("category", "general")))
            except ValueError:
                category = PlaybookCategory.GENERAL

            # Parse variables
            variables = [
                _parse_variable(v) for v in data.get("variables", []) if isinstance(v, dict)
            ]

            playbook = Playbook(
                id=f"builtin-{yaml_file.stem}",
                title=str(data["title"]),
                description=str(data.get("description", "")),
                category=category,
                platforms=platforms,
                variables=variables,
                pre_checks=[str(c) for c in data.get("pre_checks", [])],
                steps=[str(s) for s in data.get("steps", [])],
                post_checks=[str(c) for c in data.get("post_checks", [])],
                rollback=[str(r) for r in data.get("rollback", [])],
                builtin=True,
                created_at=datetime.now(UTC),
            )
            playbooks.append(playbook)
            logger.debug("Loaded builtin playbook: %s", playbook.title)

        except Exception:
            logger.exception("Failed to load playbook template: %s", yaml_file.name)

    return playbooks
