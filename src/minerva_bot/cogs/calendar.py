"""Calendar cog — announces events 10 minutes before they start."""

from __future__ import annotations

import html
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

# How many minutes before an event starts to send the announcement.
_ANNOUNCE_BEFORE_MINUTES = 10

# Width of the detection window (±1 min around the target offset).
# The loop runs every minute, so a 2-minute window ensures nothing is missed.
_WINDOW_MINUTES = 2

_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"


def _format_time_range(start_str: str, end_str: str, timezone_name: str = "") -> str:
    """Return a formatted time range string, e.g. '2:00 PM - 3:30 PM (America/Los_Angeles)'."""
    if not start_str or not end_str:
        return ""
    try:
        start_dt = datetime.fromisoformat(start_str)
        end_dt = datetime.fromisoformat(end_str)
    except ValueError:
        return ""
    if timezone_name:
        try:
            tz = ZoneInfo(timezone_name)
            start_dt = start_dt.astimezone(tz)
            end_dt = end_dt.astimezone(tz)
            tz_str = f" ({start_dt.strftime('%Z')})"
        except ZoneInfoNotFoundError:
            tz_str = f" ({timezone_name})"
    else:
        offset = start_dt.utcoffset()
        if offset is not None:
            total_hours = int(offset.total_seconds()) // 3600
            tz_str = f" (UTC{'+' if total_hours >= 0 else ''}{total_hours})"
        else:
            tz_str = ""
    return f"{start_dt.strftime('%-I:%M %p')} - {end_dt.strftime('%-I:%M %p')}{tz_str}"


def _clean_html(text: str) -> str:
    """Strip HTML tags and unescape entities from Google Calendar descriptions."""
    text = re.sub(r"<[^>]+>", " ", text)  # remove tags
    text = html.unescape(text)  # &amp; → &, &lt; → <, etc.
    return " ".join(text.split())  # collapse whitespace


class CalendarCog(commands.Cog):
    """Polls Google Calendar and announces upcoming events in Discord."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._announced: set[str] = set()
        self.check_events.start()

    async def cog_unload(self) -> None:
        self.check_events.cancel()

    @tasks.loop(minutes=1)
    async def check_events(self) -> None:
        settings = self.bot.settings  # type: ignore[attr-defined]

        if not settings.google_calendar_api_key or not settings.google_calendar_id:
            return
        if settings.announcement_channel_id is None:
            return

        channel = self.bot.get_channel(settings.announcement_channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                "Announcement channel %s not found or not a text channel",
                settings.announcement_channel_id,
            )
            return

        now = datetime.now(UTC)
        target = now + timedelta(minutes=_ANNOUNCE_BEFORE_MINUTES)
        time_min = (target - timedelta(minutes=1)).isoformat()
        time_max = (target + timedelta(minutes=_WINDOW_MINUTES - 1)).isoformat()

        url = _CALENDAR_API_BASE.format(
            calendar_id=quote(settings.google_calendar_id, safe=""),
        )
        params = {
            "key": settings.google_calendar_api_key,
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min,
            "timeMax": time_max,
        }

        try:
            async with aiohttp.ClientSession() as session, session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Google Calendar API returned status %s", resp.status)
                    return
                data = await resp.json()
        except aiohttp.ClientError:
            logger.exception("Failed to fetch Google Calendar events")
            return

        for item in data.get("items", []):
            event_id = item.get("id", "")
            if event_id in self._announced:
                continue

            title = item.get("summary", "Untitled event")
            location = item.get("location", "")
            description = _clean_html(item.get("description", ""))
            start_raw = item.get("start", {})
            end_raw = item.get("end", {})
            start_str = start_raw.get("dateTime") or start_raw.get("date", "")
            end_str = end_raw.get("dateTime") or end_raw.get("date", "")
            timezone_name = start_raw.get("timeZone", "")
            time_range = _format_time_range(start_str, end_str, timezone_name)

            role_mention = (
                f"<@&{settings.announcement_role_id}>" if settings.announcement_role_id else ""
            )
            lines = []
            if role_mention:
                lines.append(role_mention)
            lines.append(f"🔔 **{title}** starts in {_ANNOUNCE_BEFORE_MINUTES} minutes! 🔔")
            if time_range:
                lines.append(f"🕐 {time_range} PST")
            if location:
                lines.append(f"📍 {location}")
            if description:
                lines.append(f"{description}")

            try:
                await channel.send("\n".join(lines))
                self._announced.add(event_id)
                logger.info("Announced event %r (%s)", title, event_id)
            except discord.HTTPException:
                logger.exception("Failed to send announcement for event %r", title)

    @check_events.before_loop
    async def before_check_events(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CalendarCog(bot))
