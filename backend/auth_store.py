"""User and API key persistence — in-memory + SQLite backends.

Follows the same dual-store pattern as audit_store.py.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol, runtime_checkable

from backend.models import APIKey, User


@runtime_checkable
class AuthStoreProtocol(Protocol):
    async def create_user(self, user: User) -> None: ...
    def get_user(self, user_id: str) -> User | None: ...
    def get_user_by_username(self, username: str) -> User | None: ...
    def list_users(self) -> list[User]: ...
    async def update_user(self, user: User) -> None: ...
    async def create_api_key(self, key: APIKey) -> None: ...
    def get_api_key(self, key_id: str) -> APIKey | None: ...
    def get_api_key_by_hash(self, key_hash: str) -> APIKey | None: ...
    def list_api_keys(self, user_id: str) -> list[APIKey]: ...
    async def delete_api_key(self, key_id: str) -> bool: ...


class AuthStore:
    """In-memory auth store."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._users_by_name: dict[str, str] = {}  # username -> user_id
        self._api_keys: dict[str, APIKey] = {}
        self._api_keys_by_hash: dict[str, str] = {}  # key_hash -> key_id
        self._lock = asyncio.Lock()

    async def create_user(self, user: User) -> None:
        async with self._lock:
            self._users[user.id] = user
            self._users_by_name[user.username] = user.id

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        uid = self._users_by_name.get(username)
        if uid is None:
            return None
        return self._users.get(uid)

    def list_users(self) -> list[User]:
        return list(self._users.values())

    async def update_user(self, user: User) -> None:
        async with self._lock:
            self._users[user.id] = user
            self._users_by_name[user.username] = user.id

    async def create_api_key(self, key: APIKey) -> None:
        async with self._lock:
            self._api_keys[key.id] = key
            self._api_keys_by_hash[key.key_hash] = key.id

    def get_api_key(self, key_id: str) -> APIKey | None:
        return self._api_keys.get(key_id)

    def get_api_key_by_hash(self, key_hash: str) -> APIKey | None:
        kid = self._api_keys_by_hash.get(key_hash)
        if kid is None:
            return None
        return self._api_keys.get(kid)

    def list_api_keys(self, user_id: str) -> list[APIKey]:
        return [k for k in self._api_keys.values() if k.user_id == user_id]

    async def delete_api_key(self, key_id: str) -> bool:
        async with self._lock:
            key = self._api_keys.pop(key_id, None)
            if key is None:
                return False
            self._api_keys_by_hash.pop(key.key_hash, None)
            return True


class SQLiteAuthStore:
    """SQLite-backed auth store."""

    def __init__(self, db_path: Path) -> None:
        from backend.store_sqlite import _open_db

        self._conn = _open_db(db_path)
        self._lock = asyncio.Lock()

    async def create_user(self, user: User) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT INTO users"
                " (id, username, password_hash, role, created_at, disabled, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user.id,
                    user.username,
                    user.password_hash,
                    user.role,
                    user.created_at.isoformat(),
                    int(user.disabled),
                    user.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get_user(self, user_id: str) -> User | None:
        row = self._conn.execute("SELECT data FROM users WHERE id = ?", (user_id,)).fetchone()
        return User.model_validate_json(row[0]) if row else None

    def get_user_by_username(self, username: str) -> User | None:
        row = self._conn.execute(
            "SELECT data FROM users WHERE username = ?", (username,)
        ).fetchone()
        return User.model_validate_json(row[0]) if row else None

    def list_users(self) -> list[User]:
        rows = self._conn.execute("SELECT data FROM users ORDER BY created_at DESC").fetchall()
        return [User.model_validate_json(r[0]) for r in rows]

    async def update_user(self, user: User) -> None:
        async with self._lock:
            self._conn.execute(
                "UPDATE users SET password_hash = ?, role = ?, disabled = ?, data = ? WHERE id = ?",
                (
                    user.password_hash,
                    user.role,
                    int(user.disabled),
                    user.model_dump_json(),
                    user.id,
                ),
            )
            self._conn.commit()

    async def create_api_key(self, key: APIKey) -> None:
        async with self._lock:
            self._conn.execute(
                "INSERT INTO api_keys"
                " (id, key_hash, label, user_id, role, created_at, expires_at, disabled, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key.id,
                    key.key_hash,
                    key.label,
                    key.user_id,
                    key.role,
                    key.created_at.isoformat(),
                    key.expires_at.isoformat() if key.expires_at else None,
                    int(key.disabled),
                    key.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get_api_key(self, key_id: str) -> APIKey | None:
        row = self._conn.execute("SELECT data FROM api_keys WHERE id = ?", (key_id,)).fetchone()
        return APIKey.model_validate_json(row[0]) if row else None

    def get_api_key_by_hash(self, key_hash: str) -> APIKey | None:
        row = self._conn.execute(
            "SELECT data FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        return APIKey.model_validate_json(row[0]) if row else None

    def list_api_keys(self, user_id: str) -> list[APIKey]:
        rows = self._conn.execute(
            "SELECT data FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [APIKey.model_validate_json(r[0]) for r in rows]

    async def delete_api_key(self, key_id: str) -> bool:
        async with self._lock:
            cur = self._conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            self._conn.commit()
            return cur.rowcount > 0


def make_auth_store() -> AuthStore | SQLiteAuthStore:
    """Factory: returns SQLiteAuthStore when DB_PATH is set, else in-memory."""
    from backend.config import settings

    if settings.db_path:
        return SQLiteAuthStore(Path(settings.db_path))
    return AuthStore()
