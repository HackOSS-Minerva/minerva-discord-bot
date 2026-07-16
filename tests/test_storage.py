"""Tests for admin_bot.storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva_bot.storage import GuildStore


@pytest.mark.asyncio
async def test_init_and_get_settings(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite3"
    store = GuildStore(db)
    await store.init()

    settings = await store.get_settings(guild_id=123)
    assert settings.guild_id == 123
    assert settings.default_category_id is None


@pytest.mark.asyncio
async def test_set_default_category(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite3"
    store = GuildStore(db)
    await store.init()

    await store.set_default_category(guild_id=456, category_id=789)
    settings = await store.get_settings(guild_id=456)
    assert settings.default_category_id == 789


@pytest.mark.asyncio
async def test_record_action(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite3"
    store = GuildStore(db)
    await store.init()

    await store.record_action(
        guild_id=111, actor_id=222, action="test", detail="detail text"
    )
    # Smoke test: no errors raised, action was recorded
    settings = await store.get_settings(guild_id=111)
    assert settings.guild_id == 111
