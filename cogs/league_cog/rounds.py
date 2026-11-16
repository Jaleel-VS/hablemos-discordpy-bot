"""Round lifecycle management — end processing, winner selection, announcements."""
import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import discord

from cogs.league_cog.config import (
    CHAMPION_ROLE_ID,
    WINNER_CHANNEL_ID,
)
from cogs.league_cog.league_helper.round_end_image import render_round_end
from cogs.utils.guild import HOME_GUILD_ID

logger = logging.getLogger(__name__)


def enrich_top_entries(entries: list[dict], *, bot) -> list[dict]:
    """Attach ``avatar_url`` to raw leaderboard rows.

    Avatars are resolved from the bot's user cache; uncached users fall
    back to ``None`` which the image renderer turns into a default avatar.
    Keeping this pure-python (no ``await``) means the caller can run the
    whole render — enrichment + drawing — inside one ``asyncio.to_thread`` hop.
    """
    out: list[dict] = []
    for e in entries:
        user = bot.get_user(e["user_id"])
        out.append({
            "rank": int(e["rank"]),
            "user_id": e["user_id"],
            "username": e["username"],
            "total_score": int(e["total_score"]),
            "avatar_url": str(user.display_avatar.url) if user else None,
        })
    return out


def get_eligible_champions(top_list: list, cooldown_set: set, count: int = 3) -> list:
    """Get top N users from a leaderboard who aren't on cooldown."""
    eligible = []
    for entry in top_list:
        if entry['user_id'] not in cooldown_set:
            eligible.append(entry)
            if len(eligible) >= count:
                break
    return eligible


def build_round_end_announcement(
    round_number: int,
    spanish_top3: list,
    english_top3: list,
    spanish_champions: list,
    english_champions: list,
    last_round_recipients: set,
) -> str:
    """Build the round-end announcement message text."""
    medals = ["🥇", "🥈", "🥉"]

    lines = [
        f"# 🏆 Round {round_number} has ended! 🏆",
        "",
        "Congratulations to this week's top performers!",
        "",
    ]

    if spanish_top3:
        lines.append("## 🇪🇸 Spanish League")
        for i, entry in enumerate(spanish_top3):
            on_cooldown = " *(resting)*" if entry['user_id'] in last_round_recipients else ""
            lines.append(f"{medals[i]} <@{entry['user_id']}> — **{entry['total_score']}** pts{on_cooldown}")
        lines.append("")

    if english_top3:
        lines.append("## 🇬🇧 English League")
        for i, entry in enumerate(english_top3):
            on_cooldown = " *(resting)*" if entry['user_id'] in last_round_recipients else ""
            lines.append(f"{medals[i]} <@{entry['user_id']}> — **{entry['total_score']}** pts{on_cooldown}")
        lines.append("")

    champion_mentions = []
    seen_ids = set()
    for entry in spanish_champions + english_champions:
        if entry['user_id'] not in seen_ids:
            champion_mentions.append(f"<@{entry['user_id']}>")
            seen_ids.add(entry['user_id'])

    if champion_mentions:
        lines.append("## ⭐ Weekly Champions ⭐")
        lines.append(f"This week's <@&{CHAMPION_ROLE_ID}> goes to:")
        lines.append(", ".join(champion_mentions))
        lines.append("")
        lines.append("-# To keep things fair, champions take a 1-week break before they can earn the role again — but they can still compete for the top spots!")
        lines.append("")

    lines.append(f"*Round {round_number} • See you next round!* 🔥")
    lines.append("-# Run `$help league` for more info")

    return "\n".join(lines)


def next_round_end(now: datetime) -> datetime:
    """Return the end of a round starting at ``now``: the next Sunday, 12:00 UTC.

    A round started on a Sunday runs to the following Sunday.
    """
    days_until_sunday = (6 - now.weekday()) % 7 or 7
    next_sunday = now + timedelta(days=days_until_sunday)
    return next_sunday.replace(hour=12, minute=0, second=0, microsecond=0)


async def process_round_end(
    bot, current_round: dict, *, on_next_round: Callable[[dict], None],
) -> dict | None:
    """
    Full round-end processing: save winners, create the next round, manage roles, announce.

    The database writes run in one transaction before any Discord call, so a
    failure or restart can't leave the league without an active round.
    ``on_next_round`` receives the new round as soon as it is committed, so
    messages scored during the role and announcement awaits land in it.
    Returns a summary for the caller, or ``None`` if the round was already
    completed by another caller (nothing is changed).
    """
    round_id = current_round['round_id']
    round_number = current_round['round_number']

    logger.info("Ending round %s (ID: %s)", round_number, round_id)

    guild = bot.get_guild(HOME_GUILD_ID)
    champion_role = guild.get_role(CHAMPION_ROLE_ID) if guild else None

    if not guild:
        logger.error("Could not find league guild during round end")
    if guild and not champion_role:
        logger.warning("Champion role %s not found. Continuing without role assignment.", CHAMPION_ROLE_ID)

    last_round_recipients = await bot.db.get_last_round_role_recipients()

    spanish_top = await bot.db.get_leaderboard('spanish', limit=10, round_id=round_id)
    english_top = await bot.db.get_leaderboard('english', limit=10, round_id=round_id)

    spanish_top3 = spanish_top[:3]
    english_top3 = english_top[:3]

    winners_data = []
    for league_type, top3 in [('spanish', spanish_top3), ('english', english_top3)]:
        for rank, entry in enumerate(top3, start=1):
            winners_data.append({
                'user_id': entry['user_id'],
                'username': entry['username'],
                'league_type': league_type,
                'rank': rank,
                'total_score': entry['total_score'],
                'active_days': entry['active_days'],
            })

    spanish_champions = get_eligible_champions(spanish_top, last_round_recipients)
    english_champions = get_eligible_champions(english_top, last_round_recipients)

    new_role_recipient_ids = list(dict.fromkeys(
        e['user_id'] for e in spanish_champions + english_champions
    ))

    now = datetime.now(UTC)
    next_end = next_round_end(now)
    next_round_id = await bot.db.complete_round(
        round_id, winners_data, new_role_recipient_ids, round_number + 1, now, next_end,
    )
    if next_round_id is None:
        logger.warning("Round %s (ID: %s) was already completed; skipping", round_number, round_id)
        return None
    logger.info("Created next round %s (ID: %s): %s to %s", round_number + 1, next_round_id, now, next_end)
    on_next_round({
        'round_id': next_round_id,
        'round_number': round_number + 1,
        'start_date': now,
        'end_date': next_end,
        'status': 'active',
    })

    roles_added = []
    roles_removed = []

    if champion_role and guild:
        for user_id in last_round_recipients:
            try:
                member = guild.get_member(user_id)
                if member and champion_role in member.roles:
                    await member.remove_roles(champion_role, reason=f"Round {round_number} ended - champion cooldown")
                    roles_removed.append(user_id)
            except Exception as e:
                logger.error("Failed to remove champion role from %s: %s", user_id, e)

        for user_id in new_role_recipient_ids:
            try:
                member = guild.get_member(user_id)
                if member and champion_role not in member.roles:
                    await member.add_roles(champion_role, reason=f"Round {round_number} champion")
                    roles_added.append(user_id)
            except Exception as e:
                logger.error("Failed to add champion role to %s: %s", user_id, e)

    try:
        channel = bot.get_channel(WINNER_CHANNEL_ID)
        if channel:
            message = build_round_end_announcement(
                round_number=round_number,
                spanish_top3=spanish_top3,
                english_top3=english_top3,
                spanish_champions=spanish_champions,
                english_champions=english_champions,
                last_round_recipients=last_round_recipients,
            )

            # Render the podium image. We use the top 6 of each league
            # (top 3 on the podium, ranks 4-6 as runner-up cards).
            # Rendering hits requests.get() for avatars, so keep it
            # off the event loop.
            spanish_enriched = enrich_top_entries(spanish_top[:6], bot=bot)
            english_enriched = enrich_top_entries(english_top[:6], bot=bot)
            image_file: discord.File | None = None
            try:
                buf = await asyncio.to_thread(
                    render_round_end,
                    round_number=round_number,
                    spanish_top=spanish_enriched,
                    english_top=english_enriched,
                )
                image_file = discord.File(buf, filename="round_end.png")
            except Exception as e:
                # Never block the text announcement on image-render failures.
                logger.error(
                    "Failed to render round-end image for round %s: %s",
                    round_number, e, exc_info=True,
                )

            if image_file is not None:
                await channel.send(message, file=image_file)
            else:
                await channel.send(message)
            logger.info("Announced round %s winners in channel %s", round_number, WINNER_CHANNEL_ID)
        else:
            logger.error("Could not find winner announcement channel %s", WINNER_CHANNEL_ID)
    except discord.HTTPException as e:
        logger.error("HTTP error announcing winners: %s", e, exc_info=True)
    except Exception as e:
        logger.error("Error announcing winners: %s", e, exc_info=True)

    return {
        'round_number': round_number,
        'spanish_top3': spanish_top3,
        'english_top3': english_top3,
        'roles_added': roles_added,
        'roles_removed': roles_removed,
        'next_round_number': round_number + 1,
        'next_end': next_end,
    }


async def ensure_round_exists(bot) -> None:
    """Create initial round if none exists."""
    try:
        current_round = await bot.db.get_current_round()
        if not current_round:
            start_date = datetime.now(UTC)
            end_date = next_round_end(start_date)

            round_id = await bot.db.create_round(1, start_date, end_date)
            logger.info("Created initial round %s: %s to %s", round_id, start_date, end_date)
    except Exception as e:
        logger.error("Error ensuring round exists: %s", e, exc_info=True)
