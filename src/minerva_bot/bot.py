"""Bot client definition."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from minerva_bot.checks import NotServerAdmin
from minerva_bot.config import Settings
from minerva_bot.storage import GuildStore

logger = logging.getLogger(__name__)

_INITIAL_EXTENSIONS = ("minerva_bot.cogs.admin",)


class MinervaBot(commands.Bot):
    """The bot instance.

    One process, many guilds: this class holds no per-guild state on
    `self` (that would leak between tenants). Anything guild-specific goes
    through `self.store`, which is scoped by `guild_id` on every call.
    """

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

        self.settings = settings
        self.store = GuildStore(settings.database_path)

    async def setup_hook(self) -> None:
        await self.store.init()

        for extension in _INITIAL_EXTENSIONS:
            await self.load_extension(extension)

        if self.settings.dev_guild_id is not None:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced commands to dev guild %s", self.settings.dev_guild_id)
        else:
            await self.tree.sync()
            logger.info("Synced commands globally")

        self.tree.on_error = self._on_app_command_error  # type: ignore[method-assign]

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info(
            "Logged in as %s (id=%s), serving %d guild(s)",
            self.user.name,
            self.user.id,
            len(self.guilds),
        )

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, NotServerAdmin | app_commands.MissingPermissions):
            message = str(error) or "You don't have permission to use this command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            message = (
                "I'm missing permissions to do that in this server: "
                f"{', '.join(error.missing_permissions)}"
            )
        else:
            logger.exception("Unhandled app command error", exc_info=error)
            message = "Something went wrong running that command."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
