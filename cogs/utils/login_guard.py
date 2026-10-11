"""Keep a rejected Discord login from turning into a restart loop.

When Discord rejects the login, ``bot.run`` raises and the process exits.
The container platform restarts it at once, and every restart logs in
again. Discord resets the bot token after 1000 logins in a day, so a
rejected login can lock the bot out for good. Waiting before the exit
keeps the restart rate low.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

import discord

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 30 * 60


def run_with_login_guard(
    run: Callable[[], None],
    *,
    delay: float = RETRY_DELAY_SECONDS,
    sleep: Callable[[float], object] = time.sleep,
) -> None:
    """Call ``run`` (a blocking ``bot.run``). Wait, then exit, if Discord rejects the login.

    Any other exception propagates unchanged. A clean return is a clean return.
    """
    try:
        run()
        return
    except discord.PrivilegedIntentsRequired:
        logger.error(
            "Discord rejected the privileged intents (members, presences, message content). "
            "Enable them in the Developer Portal or request access. "
            "Waiting %s minutes before exiting so the restart loop doesn't use up the login limit.",
            round(delay / 60),
        )
    except discord.LoginFailure:
        logger.error(
            "Discord rejected the bot token. Reset it in the Developer Portal and update the "
            "BOT_TOKEN secret. "
            "Waiting %s minutes before exiting so the restart loop doesn't use up the login limit.",
            round(delay / 60),
        )
    sleep(delay)
    raise SystemExit(1)
