"""Bulk provisioning: create the full role + channel layout at once.

``/use-template`` replays a data-driven template so an admin can stand up a
whole server from one command. The layout is declared as data at the bottom of
this module (roles, categories, and each category's privacy policy), which
keeps it easy to tweak. Like every other command, it only ever touches the
guild it was invoked from.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from minerva_bot.checks import require_admin

if TYPE_CHECKING:
    from minerva_bot.bot import MinervaBot

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    """A channel inside a template category."""

    name: str
    kind: str = "text"  # "text" or "forum"


@dataclass(frozen=True, slots=True)
class CategorySpec:
    """A category and the channels it contains."""

    name: str
    # None = public; otherwise the tuple of role names allowed to view it.
    allow: tuple[str, ...] | None
    channels: tuple[ChannelSpec, ...]


@dataclass(frozen=True, slots=True)
class RoleSpec:
    """A role to create, with its permissions."""

    name: str
    color: int
    permissions: discord.Permissions


# Roles, declared highest-privilege first (also the order used in the summary).
_ROLES: tuple[RoleSpec, ...] = (
    RoleSpec(
        name="admin",
        color=0xED4245,
        permissions=discord.Permissions(administrator=True),
    ),
    RoleSpec(
        name="lead",
        color=0xF1C40F,
        permissions=discord.Permissions(
            kick_members=True,
            ban_members=True,
            manage_channels=True,
            manage_messages=True,
            manage_nicknames=True,
            moderate_members=True,
            manage_events=True,
        ),
    ),
    RoleSpec(
        name="workshop lead",
        color=0xE67E22,
        permissions=discord.Permissions(
            manage_channels=True,
            manage_messages=True,
            manage_nicknames=True,
            moderate_members=True,
        ),
    ),
    RoleSpec(
        name="judge",
        color=0x9B59B6,
        permissions=discord.Permissions(
            manage_messages=True,
            moderate_members=True,
        ),
    ),
    RoleSpec(
        name="mentor",
        color=0x3498DB,
        permissions=discord.Permissions(
            manage_messages=True,
            moderate_members=True,
        ),
    ),
    RoleSpec(
        name="participant",
        color=0x2ECC71,
        permissions=discord.Permissions(),
    ),
)

# Roles allowed into "participant-and-above" (private) channels.
_PARTICIPANT_UP: tuple[str, ...] = (
    "participant",
    "mentor",
    "judge",
    "workshop lead",
    "lead",
    "admin",
)
# Roles allowed into organizer-only channels.
_LEAD_UP: tuple[str, ...] = ("lead", "admin")


_CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec(
        name="info desk",
        allow=None,
        channels=(
            ChannelSpec("announcements"),
            ChannelSpec("rules"),
            ChannelSpec("welcome"),
            ChannelSpec("role-request"),
            ChannelSpec("resources"),
            ChannelSpec("faq"),
        ),
    ),
    CategorySpec(
        name="workshops",
        allow=_PARTICIPANT_UP,
        channels=(ChannelSpec("resources"),),
    ),
    CategorySpec(
        name="help desk",
        allow=_PARTICIPANT_UP,
        channels=(ChannelSpec("team-formation", kind="forum"),),
    ),
    CategorySpec(
        name="general",
        allow=_PARTICIPANT_UP,
        channels=(
            ChannelSpec("introductions"),
            ChannelSpec("talk-to-organizers"),
            ChannelSpec("general"),
            ChannelSpec("linkedin"),
            ChannelSpec("github"),
            ChannelSpec("devpost"),
            ChannelSpec("off-topic"),
        ),
    ),
    CategorySpec(
        name="mentors",
        allow=_PARTICIPANT_UP,
        channels=(
            ChannelSpec("introductions"),
            ChannelSpec("ask-mentors"),
        ),
    ),
    CategorySpec(
        name="organizers",
        allow=_LEAD_UP,
        channels=(
            ChannelSpec("general"),
            ChannelSpec("workshops"),
            ChannelSpec("mentors"),
            ChannelSpec("judges"),
            ChannelSpec("verification"),
            ChannelSpec("logs"),
        ),
    ),
)


def _role_overwrites(
    guild: discord.Guild, allow: tuple[str, ...] | None
) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
    """Build the category overwrites for a privacy policy.

    A public category returns an empty dict (discord.py requires a real dict
    or no argument; passing ``None`` raises ``TypeError``). A non-None
    ``allow`` hides the category from @everyone and grants view to each role.
    """
    if allow is None:
        return {}

    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }
    for name in allow:
        role = discord.utils.get(guild.roles, name=name)
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
    return overwrites


class TemplateCog(commands.Cog):
    """Admin command that provisions the whole server layout from a template."""

    def __init__(self, bot: MinervaBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="use-template",
        description="Create this server's full role and channel layout from the template.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @require_admin()
    @app_commands.checks.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def use_template(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        guild = interaction.guild

        # Creating many roles + channels can take a moment; defer so Discord
        # doesn't time out the interaction.
        await interaction.response.defer(ephemeral=True)

        # --- Roles (reuse an existing role with the same name) ---
        roles: dict[str, discord.Role] = {}
        for role_spec in _ROLES:
            existing = discord.utils.get(guild.roles, name=role_spec.name)
            if existing is not None:
                roles[role_spec.name] = existing
                continue
            roles[role_spec.name] = await guild.create_role(
                name=role_spec.name,
                color=discord.Color(role_spec.color),
                hoist=True,
                mentionable=True,
                permissions=role_spec.permissions,
                reason=f"Created via /use-template by {interaction.user}",
            )

        # --- Categories + channels (reuse existing categories) ---
        created_categories = 0
        created_channels = 0
        for cat_spec in _CATEGORIES:
            if discord.utils.get(guild.categories, name=cat_spec.name) is not None:
                logger.warning("Category %r already exists; skipping", cat_spec.name)
                continue
            category = await guild.create_category(
                name=cat_spec.name,
                overwrites=_role_overwrites(guild, cat_spec.allow),  # type: ignore[arg-type]
                reason=f"Created via /use-template by {interaction.user}",
            )
            created_categories += 1

            for ch_spec in cat_spec.channels:
                if discord.utils.get(category.channels, name=ch_spec.name) is not None:
                    logger.warning(
                        "Channel %r already exists in %r; skipping",
                        ch_spec.name,
                        cat_spec.name,
                    )
                    continue
                if ch_spec.kind == "forum":
                    await guild.create_forum(
                        name=ch_spec.name,
                        category=category,
                        reason=f"Created via /use-template by {interaction.user}",
                    )
                else:
                    await guild.create_text_channel(
                        name=ch_spec.name,
                        category=category,
                        reason=f"Created via /use-template by {interaction.user}",
                    )
                created_channels += 1

        await self.bot.store.record_action(
            guild_id=guild.id,
            actor_id=interaction.user.id,
            action="use_template",
            detail=(
                f"roles={len(roles)} categories={created_categories} channels={created_channels}"
            ),
        )

        role_mentions = " -> ".join(roles[role_spec.name].mention for role_spec in _ROLES)
        await interaction.followup.send(
            f"Template applied in **{guild.name}**.{chr(10)}"
            f"**Roles (highest to lowest):** {role_mentions}{chr(10)}"
            f"**Created:** {created_categories} categories, {created_channels} channels.",
            ephemeral=True,
        )


async def setup(bot: MinervaBot) -> None:
    await bot.add_cog(TemplateCog(bot))
