"""Entry point: `uv run minerva-bot` or `python -m minerva_bot`."""

from __future__ import annotations

from minerva_bot.bot import MinervaBot
from minerva_bot.config import get_settings
from minerva_bot.logging_config import configure_logging


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    bot = MinervaBot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    run()
