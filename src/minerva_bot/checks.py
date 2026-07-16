"""Authorization checks shared across cogs.

Admin-only enforcement is layered twice on purpose:

1. `default_permissions(administrator=True)` on each command hides it from
   the Discord UI for non-admins and blocks invocation at Discord's level.
2. `require_admin()` re-checks at runtime, because per-guild admins can
   override a command's default permissions in Server Settings -> Integrations.
   Without the runtime check, a server owner could grant the command to a
   non-admin role and this bot would honor it. We don't want that: the
   contract is "server administrators only", full stop, in every guild.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import discord
from discord import app_commands

_T = TypeVar("_T")


class NotServerAdmin(app_commands.CheckFailure):
    """Raised when a non-administrator invokes an admin-only command."""


def require_admin() -> Callable[[_T], _T]:
    """App-command check: caller must have the Administrator permission
    *in the guild the command was invoked from*.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise NotServerAdmin("This command can only be used inside a server.")

        member = interaction.user
        if not isinstance(member, discord.Member):
            raise NotServerAdmin("Could not resolve your server membership.")

        if not member.guild_permissions.administrator:
            raise NotServerAdmin(
                "You must be a server administrator to use this command."
            )

        return True

    return app_commands.check(predicate)
