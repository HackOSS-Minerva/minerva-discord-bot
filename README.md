# Minerva Discord Bot

A Discord bot for server administration — create roles, channels, and categories via slash commands. Built with Python 3.14, [discord.py](https://github.com/Rapptz/discord.py), and [uv](https://docs.astral.sh/uv/).

> **Baseline features:** `/create-role`, `/create-channel`, and `/create-category` (admin only). More commands coming soon.

## Commands

All commands are admin-only. Non-admins won't see them in Discord's UI, and a runtime check re-verifies permissions before executing.

| Command | Description |
|---|---|
| `/create-role name [color] [mentionable] [hoist]` | Creates a role. Defaults when omitted: `color` white, `mentionable` and `hoist` yes. `color` accepts hex like `#5865F2`. |
| `/create-channel name type [category] [topic] [private]` | Creates a channel. `type` (Text, Announcement, Voice, Stage, Forum) and `category` are chosen from dropdown menus. If `private` is set, only administrators can view it. |
| `/create-category name [private]` | Creates a channel category. If `private` is set, only administrators can view it. |

## Welcome messages

When a new member joins, the bot greets them in the channel with ID `1534742096307552306` (hardcoded for now):

> Hello @member! Welcome to [server name]!
> Check out the rules to get started and assign yourself a role!

The bot must have permission to send messages in that channel, and the **Members** intent must be enabled (see setup above).

## Requirements

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- A Discord application + bot token: https://discord.com/developers/applications

### Bot setup in the Discord Developer Portal

1. Create an application, then add a **Bot** to it.
2. Under **Bot**, copy the token into `.env` (see below). Keep this secret.
3. Enable the privileged **Members** intent under **Bot** — it is required so the bot fires `on_member_join` and can send welcome messages.
4. Under **OAuth2 -> URL Generator**, select the `bot` and `applications.commands` scopes, and at minimum the **Manage Roles** and **Manage Channels** bot permissions. Use the generated URL to invite the bot to a server.
5. **Role hierarchy note:** Discord only lets a bot manage roles *below* its own highest role. Make sure the bot's role sits above any roles you want it to manage.

## Local development

```bash
git clone https://github.com/HackOSS-Minerva/minerva-discord-bot.git
cd minerva-discord-bot
cp .env.example .env   # then fill in DISCORD_TOKEN, and DEV_GUILD_ID for instant command sync
uv sync --all-groups
uv run minerva-bot
```

Setting `DEV_GUILD_ID` in `.env` to a test server's ID makes slash commands appear there instantly. Leave it unset in production; commands then sync globally, which can take up to ~1 hour to propagate.

## Development workflow

```bash
uv run ruff format .        # format
uv run ruff check . --fix   # lint
uv run mypy src tests       # type check (strict)
uv run pytest               # tests
uv build                    # build sdist + wheel
```

## Running with Docker

```bash
docker build -t minerva-bot .
docker run --rm -it \
  -e DISCORD_TOKEN=your-token-here \
  -v minerva-bot-data:/app/data \
  minerva-bot
```

## Multi-tenancy & permissions

A Discord bot is inherently multi-tenant: one running process is invited into many independent servers ("guilds"), each with its own roles, channels, members, and permission structure. This bot is built around that:

- **Every command operates only on `interaction.guild`** — the server the command was invoked from. There's no shared or global state that could leak between servers.
- **Admin-only enforcement is layered twice.** `default_permissions(administrator=True)` hides each command from non-admins in Discord's UI, and a runtime check (`minerva_bot/checks.py`) re-verifies `interaction.user.guild_permissions.administrator` in the invoking guild before doing anything.
- **Per-guild storage is scoped by `guild_id` everywhere** (`minerva_bot/storage.py`). One SQLite file backs all servers; every query filters on `guild_id`, so no tenant can see or affect another's data.

## Project layout

```
src/minerva_bot/
  __main__.py        entry point (uv run minerva-bot)
  bot.py              Bot subclass, extension loading, command sync, error handling
  config.py           typed Settings (env vars / .env)
  checks.py           admin-only authorization check
  storage.py          per-guild (multi-tenant) SQLite storage + audit log
  logging_config.py
  cogs/
    admin.py          /create-role, /create-channel, /create-category
tests/
  test_storage.py
.github/workflows/ci.yml
Dockerfile
```


