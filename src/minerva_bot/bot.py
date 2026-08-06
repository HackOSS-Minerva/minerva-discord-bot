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

_INITIAL_EXTENSIONS = ("minerva_bot.cogs.admin", "minerva_bot.cogs.template")

# Hardcoded ID of the channel where new members are greeted.
# TODO: move to per-guild `guild_settings` once it becomes configurable.
_WELCOME_CHANNEL_ID = 1534742096307552306


class MinervaBot(commands.Bot):
    """The bot instance.

    One process, many guilds: this class holds no per-guild state on
    `self` (that would leak between tenants). Anything guild-specific goes
    through `self.store`, which is scoped by `guild_id` on every call.
    """

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        # Privileged intent: required for `on_member_join` (welcome messages).
        # It must ALSO be enabled in the Discord Developer Portal (Application
        # -> Bot), or Discord refuses the connection. Gate it behind a setting
        # so the bot can still start without it (just no welcome messages).
        if settings.members_intent:
            intents.members = True
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

    async def on_member_join(self, member: discord.Member) -> None:
        """Greet a newly joined member in the configured welcome channel.

        The channel ID is hardcoded behind ``_WELCOME_CHANNEL_ID`` for now.
        """
        guild = member.guild
        channel = guild.get_channel(_WELCOME_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                "Welcome channel %s not found or not a text channel in guild %s",
                _WELCOME_CHANNEL_ID,
                guild.id,
            )
            return

        try:
            await channel.send(
                f"Hello {member.mention}! Welcome to {guild.name}!\n"
                "Check out the rules to get started and assign yourself a role!"
            )
        except discord.Forbidden:
            logger.warning(
                "Missing permissions to send welcome message in channel %s",
                channel.id,
            )
        except discord.HTTPException:
            logger.exception("Failed to send welcome message in channel %s", channel.id)

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
