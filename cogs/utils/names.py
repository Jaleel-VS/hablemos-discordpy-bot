"""Resolve Discord user IDs to readable display labels.

Discord client-side mentions (`<@id>`) only render a name when the
target user is cached by the viewer's client; for uncached members or
users who have left the guild they show as a raw `<@id>` string, which
is poor UX in leaderboards. These helpers resolve a stable plain-text
label server-side instead, falling back through progressively cheaper
sources and ending at the bare ID only when every lookup fails.

Label format: ``Server Nick (username)`` when a guild nick differs from
the account username, otherwise just ``username``. Users who have left
the guild resolve to their global ``username`` (no nick); only a fully
unresolvable ID degrades to ``User 123…``.
"""
import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


def _member_label(member: discord.Member) -> str:
    """Label for a resolved guild member: ``Nick (username)`` or ``username``.

    ``display_name`` is the guild nick (or global name, or username, in
    that order). When it differs from the bare account ``name`` we show
    both so the server-facing nick is primary and the username is a
    disambiguator; when they match we avoid the redundant parenthetical.
    """
    nick = member.display_name
    username = member.name
    if nick.casefold() == username.casefold():
        return nick
    return f"{nick} ({username})"


def _user_label(user: discord.User | discord.abc.User) -> str:
    """Label for a user who is not a guild member (e.g. they left).

    Prefers the global display name when set, falling back to the bare
    username; no guild nick is available off a plain ``User``.
    """
    global_name = getattr(user, "global_name", None)
    username = user.name
    if global_name and global_name.casefold() != username.casefold():
        return f"{global_name} ({username})"
    return username


async def resolve_member_label(
    bot: commands.Bot, guild: discord.Guild, user_id: int,
) -> str:
    """Resolve ``user_id`` to a readable label, hitting the API only on a miss.

    Lookup order (cheapest first):
      1. ``guild.get_member`` — in-memory cache, no network.
      2. ``guild.fetch_member`` — one API call; covers uncached members.
      3. ``bot.get_user`` / ``bot.fetch_user`` — for users who left the
         guild but still exist on Discord (global username, no nick).
      4. Bare ``User <id>`` — every lookup failed (deleted account, API
         error); never raises so callers can format a whole leaderboard.
    """
    member = guild.get_member(user_id)
    if member is not None:
        return _member_label(member)

    try:
        member = await guild.fetch_member(user_id)
    except discord.NotFound:
        member = None
    except (discord.HTTPException, discord.Forbidden) as exc:
        logger.debug("fetch_member failed for %s in guild %s: %s", user_id, guild.id, exc)
        member = None
    if member is not None:
        return _member_label(member)

    user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except discord.NotFound:
            user = None
        except discord.HTTPException as exc:
            logger.debug("fetch_user failed for %s: %s", user_id, exc)
            user = None
    if user is not None:
        return _user_label(user)

    return f"User {user_id}"


async def resolve_member_labels(
    bot: commands.Bot, guild: discord.Guild, user_ids: list[int],
) -> dict[int, str]:
    """Resolve many IDs to labels, de-duplicating and caching within the call.

    Returns a ``{user_id: label}`` map. Resolves each distinct ID once so
    a leaderboard with repeated users (it shouldn't have them, but cheap
    insurance) never issues duplicate API calls.
    """
    labels: dict[int, str] = {}
    for user_id in dict.fromkeys(user_ids):
        labels[user_id] = await resolve_member_label(bot, guild, user_id)
    return labels
