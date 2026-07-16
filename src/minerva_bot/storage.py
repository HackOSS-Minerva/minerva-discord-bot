"""Per-guild persistent storage.

Discord bots are multi-tenant by nature: a single running process serves
many independent guilds ("servers"), each with its own roles, channels and
permissions. This module is the one place where that tenancy boundary is
enforced in code: every read/write is scoped by `guild_id`, so it is
impossible for one server's configuration or audit history to leak into
another's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    default_category_id INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    actor_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_guild ON audit_log (guild_id);
"""


@dataclass(slots=True, frozen=True)
class GuildSettings:
    """Per-tenant (per-guild) configuration."""

    guild_id: int
    default_category_id: int | None


class GuildStore:
    """Async repository for per-guild settings and audit logging.

    Every public method takes `guild_id` as its first argument and every
    query is filtered on it — that's the whole multi-tenancy contract.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def init(self) -> None:
        """Create tables if they don't exist yet. Call once at startup."""
        async with self._connect() as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await aiosqlite.connect(self._database_path)
        try:
            yield db
        finally:
            await db.close()

    async def get_settings(self, guild_id: int) -> GuildSettings:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT guild_id, default_category_id FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return GuildSettings(guild_id=guild_id, default_category_id=None)
            return GuildSettings(
                guild_id=row["guild_id"],
                default_category_id=row["default_category_id"],
            )

    async def set_default_category(
        self, guild_id: int, category_id: int | None
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO guild_settings (guild_id, default_category_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    default_category_id = excluded.default_category_id,
                    updated_at = excluded.updated_at
                """,
                (guild_id, category_id, _now_iso()),
            )
            await db.commit()

    async def record_action(
        self,
        guild_id: int,
        actor_id: int,
        action: str,
        detail: str,
    ) -> None:
        """Append an audit entry. Scoped to `guild_id`."""
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO audit_log (guild_id, actor_id, action, detail, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, actor_id, action, detail, _now_iso()),
            )
            await db.commit()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
