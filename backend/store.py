"""Session and config-dump stores.

When NETSCOPE_DB_PATH is set, SQLite-backed stores are used and sessions
survive server restarts. Otherwise, in-memory LRU stores are used.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from pathlib import Path
from typing import Protocol, runtime_checkable

from backend.config import settings
from backend.models import ConfigDump, SavedView, TopologyResult

# ---------------------------------------------------------------------------
# Protocols (define the shared interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class SessionStoreProtocol(Protocol):
    async def save(self, result: TopologyResult) -> None: ...
    def get(self, session_id: str) -> TopologyResult | None: ...
    def list_all(self) -> list[TopologyResult]: ...


@runtime_checkable
class ConfigDumpStoreProtocol(Protocol):
    async def save(self, dump: ConfigDump) -> None: ...
    def get(self, dump_id: str) -> ConfigDump | None: ...
    def list_all(self) -> list[ConfigDump]: ...
    def list_for_device(self, device_id: str) -> list[ConfigDump]: ...


@runtime_checkable
class SavedViewStoreProtocol(Protocol):
    async def save(self, view: SavedView) -> None: ...
    def get(self, view_id: str) -> SavedView | None: ...
    def list_all(self, session_id: str | None = None) -> list[SavedView]: ...
    async def delete(self, view_id: str) -> bool: ...
    async def rename(self, view_id: str, name: str) -> SavedView | None: ...


# ---------------------------------------------------------------------------
# In-memory stores (default)
# ---------------------------------------------------------------------------


class SessionStore:
    def __init__(self, max_sessions: int = settings.max_sessions) -> None:
        self._sessions: OrderedDict[str, TopologyResult] = OrderedDict()
        self._max = max_sessions
        self._lock = asyncio.Lock()

    async def save(self, result: TopologyResult) -> None:
        async with self._lock:
            if result.session_id in self._sessions:
                self._sessions.move_to_end(result.session_id)
            else:
                if len(self._sessions) >= self._max:
                    self._sessions.popitem(last=False)
            self._sessions[result.session_id] = result

    def get(self, session_id: str) -> TopologyResult | None:
        return self._sessions.get(session_id)

    def list_all(self) -> list[TopologyResult]:
        return list(reversed(self._sessions.values()))


class ConfigDumpStore:
    """Stores config dumps keyed by dump_id; queryable by device_id."""

    def __init__(self, max_dumps: int = 200) -> None:
        self._dumps: OrderedDict[str, ConfigDump] = OrderedDict()
        self._max = max_dumps
        self._lock = asyncio.Lock()

    async def save(self, dump: ConfigDump) -> None:
        async with self._lock:
            if len(self._dumps) >= self._max:
                self._dumps.popitem(last=False)
            self._dumps[dump.dump_id] = dump

    def get(self, dump_id: str) -> ConfigDump | None:
        return self._dumps.get(dump_id)

    def list_all(self) -> list[ConfigDump]:
        return list(reversed(self._dumps.values()))

    def list_for_device(self, device_id: str) -> list[ConfigDump]:
        return [d for d in reversed(self._dumps.values()) if d.device_id == device_id]


class SavedViewStore:
    """In-memory store for saved topology views."""

    def __init__(self) -> None:
        self._views: OrderedDict[str, SavedView] = OrderedDict()
        self._lock = asyncio.Lock()

    async def save(self, view: SavedView) -> None:
        async with self._lock:
            # If setting as default, clear other defaults for the same session
            if view.is_default:
                for v in self._views.values():
                    if v.session_id == view.session_id and v.view_id != view.view_id:
                        object.__setattr__(v, "is_default", False)
            self._views[view.view_id] = view

    def get(self, view_id: str) -> SavedView | None:
        return self._views.get(view_id)

    def list_all(self, session_id: str | None = None) -> list[SavedView]:
        views = list(reversed(self._views.values()))
        if session_id:
            views = [v for v in views if v.session_id == session_id]
        return views

    async def delete(self, view_id: str) -> bool:
        async with self._lock:
            return self._views.pop(view_id, None) is not None

    async def rename(self, view_id: str, name: str) -> SavedView | None:
        async with self._lock:
            view = self._views.get(view_id)
            if view is None:
                return None
            from datetime import UTC, datetime

            view = view.model_copy(update={"name": name, "updated_at": datetime.now(UTC)})
            self._views[view_id] = view
            return view


# ---------------------------------------------------------------------------
# Store factory: choose backend based on NETSCOPE_DB_PATH
# ---------------------------------------------------------------------------


def _make_stores() -> tuple[SessionStoreProtocol, ConfigDumpStoreProtocol, SavedViewStoreProtocol]:
    if settings.db_path:
        from backend.store_sqlite import (
            SQLiteConfigDumpStore,
            SQLiteSavedViewStore,
            SQLiteSessionStore,
        )

        db = Path(settings.db_path)
        vault = None
        if settings.secret_key:
            from backend.credential_vault import CredentialVault

            vault = CredentialVault(settings.secret_key)
        return (
            SQLiteSessionStore(db),
            SQLiteConfigDumpStore(db, vault=vault),
            SQLiteSavedViewStore(db),
        )
    return SessionStore(), ConfigDumpStore(), SavedViewStore()


store: SessionStoreProtocol
dump_store: ConfigDumpStoreProtocol
view_store: SavedViewStoreProtocol
store, dump_store, view_store = _make_stores()
