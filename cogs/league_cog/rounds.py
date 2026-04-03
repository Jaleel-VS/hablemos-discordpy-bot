"""Round lifecycle management — end processing, winner selection, announcements."""
import logging
from datetime import UTC, datetime, timedelta

import discord

from cogs.league_cog.config import (
    CHAMPION_ROLE_ID,
    LEAGUE_GUILD_ID,
    WINNER_CHANNEL_ID,
)

logger = logging.getLogger(__name__)


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


async def process_round_end(bot, current_round: dict) -> dict:
    """
    Full round-end processing: save winners, manage roles, announce, create next round.

    Returns dict with summary info for the caller.
    """
    round_id = current_round['round_id']
    round_number = current_round['round_number']

    logger.info("Ending round %s (ID: %s)", round_number, round_id)

    guild = bot.get_guild(LEAGUE_GUILD_ID)
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

    # Save winners
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
    if winners_data:
        await bot.db.save_round_winners(round_id, winners_data)

    await bot.db.end_round(round_id)

    spanish_champions = get_eligible_champions(spanish_top, last_round_recipients)
    english_champions = get_eligible_champions(english_top, last_round_recipients)

    new_role_recipient_ids = list(dict.fromkeys(
        e['user_id'] for e in spanish_champions + english_champions
    ))

    # Role management
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

    if new_role_recipient_ids:
        await bot.db.mark_role_recipients(round_id, new_role_recipient_ids)

    # Announce
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
            await channel.send(message)
            logger.info("Announced round %s winners in channel %s", round_number, WINNER_CHANNEL_ID)
        else:
            logger.error("Could not find winner announcement channel %s", WINNER_CHANNEL_ID)
    except discord.HTTPException as e:
        logger.error("HTTP error announcing winners: %s", e, exc_info=True)
    except Exception as e:
        logger.error("Error announcing winners: %s", e, exc_info=True)

    # Create next round
    now = datetime.now(UTC)
    days_until_sunday = (6 - now.weekday()) % 7
    if days_until_sunday == 0:
        days_until_sunday = 7
    next_sunday = now + timedelta(days=days_until_sunday)
    next_end = next_sunday.replace(hour=12, minute=0, second=0, microsecond=0)

    next_round_id = await bot.db.create_round(round_number + 1, now, next_end)
    logger.info("Created next round %s (ID: %s): %s to %s", round_number + 1, next_round_id, now, next_end)

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
            days_until_sunday = (6 - start_date.weekday()) % 7
            if days_until_sunday == 0:
                days_until_sunday = 7
            end_date = start_date + timedelta(days=days_until_sunday)
            end_date = end_date.replace(hour=23, minute=59, second=59)

            round_id = await bot.db.create_round(1, start_date, end_date)
            logger.info("Created initial round %s: %s to %s", round_id, start_date, end_date)
    except Exception as e:
        logger.error("Error ensuring round exists: %s", e, exc_info=True)
