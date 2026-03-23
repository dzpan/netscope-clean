"""Auto-registration of built-in vendor plugins.

Import this module to populate the global ``registry`` with all bundled plugins.
Arista is registered before Cisco because Cisco's broad "cisco" pattern would
otherwise match Arista devices that happen to mention "Cisco" in LLDP data.

YAML template plugins from ``backend/vendors/templates/`` are loaded last
(priority=90) so built-in plugins always take precedence.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.vendors import registry
from backend.vendors.arista import AristaPlugin
from backend.vendors.cisco import CiscoPlugin
from backend.vendors.template import load_templates_from_dir

logger = logging.getLogger(__name__)

# Register in specificity order (lower priority number = matched first).
# Arista must be checked before Cisco because Cisco's fallback regex is very broad.
registry.register(AristaPlugin(), priority=10)
registry.register(CiscoPlugin(), priority=50)

# Load community YAML templates (lowest priority).
_TEMPLATES_DIR = Path(__file__).parent / "templates"
for _tpl in load_templates_from_dir(_TEMPLATES_DIR):
    registry.register(_tpl, priority=90)
    logger.debug("Registered template plugin: %s", _tpl.vendor_id)
