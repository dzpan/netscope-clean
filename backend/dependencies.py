"""FastAPI dependency injection providers for stores."""

from __future__ import annotations

from backend.store import (
    ConfigDumpStoreProtocol,
    SavedViewStoreProtocol,
    SessionStoreProtocol,
    dump_store,
    store,
    view_store,
)


def get_store() -> SessionStoreProtocol:
    """DI provider for the session store."""
    return store


def get_dump_store() -> ConfigDumpStoreProtocol:
    """DI provider for the config dump store."""
    return dump_store


def get_view_store() -> SavedViewStoreProtocol:
    """DI provider for the saved view store."""
    return view_store
