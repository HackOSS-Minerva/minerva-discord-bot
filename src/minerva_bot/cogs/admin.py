"""Admin-only commands for creating roles, channels, and categories.

Every command here:
  * is restricted to server administrators (`checks.require_admin`, plus
    `default_permissions(administrator=True)` for the UI),
  * operates only on `interaction.guild` — the guild the command was
    invoked from — so behavior is identical and isolated across every
    server the bot is in,
  * requires the bot itself to hold the relevant permission in that guild
    (`app_commands.checks.bot_has_permissions`), so failures are reported
    clearly instead of surfacing as an opaque 403 from Discord.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from minerva_bot.checks import require_admin

if TYPE_CHECKING:
    from minerva_bot.bot import MinervaBot

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    """Slash commands for guild role and channel provisioning."""

    def __init__(self, bot: MinervaBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /create-role
    # ------------------------------------------------------------------
    @app_commands.command(name="create-role", description="Create a new role in this server.")
    @app_commands.describe(
        name="Name of the new role",
        color="Hex color, e.g. #5865F2 (optional, defaults to white)",
        mentionable="Whether the role can be @mentioned by everyone (default: yes)",
        hoist="Whether the role is shown separately in the member list (default: yes)",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @require_admin()
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def create_role(
        self,
        interaction: discord.Interaction,
        name: str,
        color: str | None = None,
        mentionable: bool = True,
        hoist: bool = True,
    ) -> None:
        assert interaction.guild is not None  # enforced by guild_only()

        parsed_color = discord.Color.from_rgb(255, 255, 255)
        if color is not None:
            try:
                parsed_color = discord.Color.from_str(color)
            except ValueError:
                await interaction.response.send_message(
                    f"`{color}` isn't a valid hex color. Try something like `#5865F2`.",
                    ephemeral=True,
                )
                return

        role = await interaction.guild.create_role(
            name=name,
            color=parsed_color,
            mentionable=mentionable,
            hoist=hoist,
            reason=f"Created via /create-role by {interaction.user}",
        )

        await self.bot.store.record_action(
            guild_id=interaction.guild.id,
            actor_id=interaction.user.id,
            action="create_role",
            detail=f"role_id={role.id} name={name!r}",
        )

        await interaction.response.send_message(
            f"Created role {role.mention}.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /create-channel
    # ------------------------------------------------------------------
    @app_commands.command(name="create-channel", description="Create a new channel in this server.")
    @app_commands.describe(
        name="Name of the new channel",
        type="Channel type",
        category="Category to place this channel under (optional)",
        topic="Topic text for the channel (optional)",
        private="If True, only administrators can see this channel",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Text", value="text"),
            app_commands.Choice(name="Announcement", value="announcement"),
            app_commands.Choice(name="Voice", value="voice"),
            app_commands.Choice(name="Stage", value="stage"),
            app_commands.Choice(name="Forum", value="forum"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @require_admin()
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def create_channel(
        self,
        interaction: discord.Interaction,
        name: str,
        type: str,
        category: discord.CategoryChannel | None = None,
        topic: str | None = None,
        private: bool = False,
    ) -> None:
        assert interaction.guild is not None

        guild: discord.Guild = interaction.guild
        reason = f"Created via /create-channel by {interaction.user}"

        # Category comes straight from the Discord UI dropdown; no manual
        # ID/name resolution is needed.
        resolved_category = category

        # Build permission overwrites for private channels. discord.py needs a
        # real dict (or no arg) here; an empty dict means "no overwrites" and
        # passing None would raise TypeError.
        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {}
        if private:
            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}

        channel: discord.abc.GuildChannel

        match type:
            case "text":
                channel = await guild.create_text_channel(
                    name=name,
                    category=resolved_category,
                    topic=topic or "",
                    overwrites=overwrites,  # type: ignore[arg-type]
                    reason=reason,
                )
            case "announcement":
                text_channel = await guild.create_text_channel(
                    name=name,
                    category=resolved_category,
                    topic=topic or "",
                    overwrites=overwrites,  # type: ignore[arg-type]
                    reason=reason,
                )
                await text_channel.edit(type=discord.ChannelType.news)
                channel = text_channel
            case "voice":
                channel = await guild.create_voice_channel(
                    name=name,
                    category=resolved_category,
                    overwrites=overwrites,  # type: ignore[arg-type]
                    reason=reason,
                )
            case "stage":
                channel = await guild.create_stage_channel(
                    name=name,
                    category=resolved_category,
                    overwrites=overwrites,  # type: ignore[arg-type]
                    reason=reason,
                )
            case "forum":
                channel = await guild.create_forum(
                    name=name,
                    category=resolved_category,
                    topic=topic or "",
                    overwrites=overwrites,  # type: ignore[arg-type]
                    reason=reason,
                )
            case _:
                await interaction.response.send_message("Unsupported channel type.", ephemeral=True)
                return

        await self.bot.store.record_action(
            guild_id=guild.id,
            actor_id=interaction.user.id,
            action="create_channel",
            detail=f"channel_id={channel.id} name={name!r} type={type}",
        )

        await interaction.response.send_message(
            f"Created channel {channel.mention}.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /create-category
    # ------------------------------------------------------------------
    @app_commands.command(
        name="create-category",
        description="Create a new channel category in this server.",
    )
    @app_commands.describe(
        name="Name of the new category",
        private="If True, only administrators can view this category and its channels",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @require_admin()
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def create_category(
        self, interaction: discord.Interaction, name: str, private: bool = False
    ) -> None:
        assert interaction.guild is not None

        # discord.py needs a real dict (or no arg) here, not None.
        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {}
        if private:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False)
            }

        category = await interaction.guild.create_category(
            name=name,
            overwrites=overwrites,  # type: ignore[arg-type]
            reason=f"Created via /create-category by {interaction.user}",
        )

        await self.bot.store.record_action(
            guild_id=interaction.guild.id,
            actor_id=interaction.user.id,
            action="create_category",
            detail=f"category_id={category.id} name={name!r}",
        )

        await interaction.response.send_message(
            f"Created category **{category.name}**.", ephemeral=True
        )


async def setup(bot: MinervaBot) -> None:
    await bot.add_cog(AdminCog(bot))
