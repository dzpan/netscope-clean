"""Shared helper functions used by multiple router modules."""

from __future__ import annotations

from fastapi import HTTPException

import backend.store as _store_module
from backend.models import TopologyResult


def get_session_or_404(session_id: str) -> TopologyResult:
    """Fetch a session by ID or raise 404."""
    result = _store_module.store.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    return result
