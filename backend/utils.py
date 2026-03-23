"""Shared utility functions."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def safe_close(conn: Any) -> None:
    """Close a Scrapli connection, ignoring errors."""
    try:
        await conn.close()
    except Exception:
        pass
