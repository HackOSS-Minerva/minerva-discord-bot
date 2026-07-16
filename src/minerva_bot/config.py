"""Application configuration, loaded from environment variables / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the bot.

    All values can be supplied via environment variables or a `.env` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_token: str = Field(
        ..., description="Bot token from the Discord developer portal"
    )

    dev_guild_id: int | None = Field(
        default=None,
        description="If set, slash commands sync instantly to this guild instead of globally.",
    )

    database_path: Path = Field(
        default=Path("minerva_bot.sqlite3"),
        description="SQLite file for per-guild configuration and audit log.",
    )

    log_level: str = Field(default="INFO")


def get_settings() -> Settings:
    """Return a freshly loaded Settings instance."""
    return Settings()  # type: ignore[call-arg]
