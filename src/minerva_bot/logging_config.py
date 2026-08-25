"""Logging configuration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

import discord

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s"
    " | %(filename)s:%(lineno)d | %(funcName)s | %(message)s"
)

# Discord messages are capped at 2000 chars; leave room for the code-block fences.
_DISCORD_MAX_CHARS = 1994


class DiscordLogHandler(logging.Handler):
    """Sends WARNING+ log records to a Discord text channel.

    Attach via ``attach_discord_handler`` after the bot is ready.
    """

    def __init__(self, channel: discord.TextChannel) -> None:
        super().__init__(level=logging.WARNING)
        self._channel = channel
        self.setFormatter(logging.Formatter(_LOG_FORMAT))

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        if len(msg) > _DISCORD_MAX_CHARS:
            msg = msg[:_DISCORD_MAX_CHARS]
        with contextlib.suppress(RuntimeError):
            # RuntimeError is raised when there is no running event loop
            asyncio.get_running_loop().create_task(self._channel.send(f"```\n{msg}\n```"))


def attach_discord_handler(channel: discord.TextChannel) -> None:
    """Attach a DiscordLogHandler to the root logger.

    Safe to call on reconnects — skips attachment if one is already present.
    """
    root = logging.getLogger()
    if any(isinstance(h, DiscordLogHandler) for h in root.handlers):
        return
    root.addHandler(DiscordLogHandler(channel))


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format=_LOG_FORMAT,
    )
    logging.getLogger("discord").setLevel(level)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
