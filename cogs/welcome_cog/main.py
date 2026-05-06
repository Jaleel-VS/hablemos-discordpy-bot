"""Staff-triggered welcome DM messages."""
from __future__ import annotations

import logging
from typing import Literal

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import red_embed

from .config import (
    BEGINNER_ENGLISH_CHANNEL_ID,
    BEGINNER_SPANISH_CHANNEL_ID,
    COMMUNITY_CHANNEL_IDS,
    CUSTOMIZE_MENTION,
    RAI_BOT_ID,
    STAFF_ROLE_IDS,
    STAFF_USER_IDS,
    WELCOME_CHANNEL_ID,
    WELCOME_COLOR,
)

logger = logging.getLogger(__name__)

WelcomeLanguage = Literal["en", "es"]


def _channel_mention(channel_id: int) -> str:
    """Return a Discord channel mention from an ID."""
    return f"<#{channel_id}>"


def _user_mention(user_id: int) -> str:
    """Return a Discord user mention from an ID."""
    return f"<@{user_id}>"


def _community_channel_lines() -> str:
    """Return formatted community channel lines."""
    return "\n".join(
        f"- {_channel_mention(channel_id)}"
        for channel_id in COMMUNITY_CHANNEL_IDS
    )


def _has_staff_role(member: discord.Member) -> bool:
    """Return whether a member has one of the configured staff roles."""
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)


def _is_staff_context(ctx: commands.Context) -> bool:
    """Return whether the command invoker is allowed to welcome users."""
    if ctx.guild is None:
        return False

    if ctx.author.id in STAFF_USER_IDS:
        return True

    if not isinstance(ctx.author, discord.Member):
        return False

    permissions = ctx.author.guild_permissions

    return (
        permissions.administrator
        or permissions.manage_guild
        or permissions.manage_messages
        or _has_staff_role(ctx.author)
    )

def staff_only():
    """Command check that allows only configured staff members."""

    async def predicate(ctx: commands.Context) -> bool:
        if _is_staff_context(ctx):
            return True

        raise commands.CheckFailure(
            "Only staff members can use this command."
        )

    return commands.check(predicate)


def language_from_command(invoked_with: str | None) -> WelcomeLanguage:
    """Infer welcome language from the command name."""
    if invoked_with and invoked_with.casefold() == "bienvenido":
        return "es"

    return "en"


def build_english_dm_embed(member: discord.Member) -> discord.Embed:
    """Build the English welcome DM embed."""
    embed = discord.Embed(
        title="Welcome!",
        description=(
            "Welcome to the Spanish-English Learning Server.\n\n"
            "**・Roles**\n"
            f"Start by setting up your learning profile through "
            f"{CUSTOMIZE_MENTION}.\n\n"
            "**・Stop by the following channels to start interacting with "
            "the community**\n"
            f"{_community_channel_lines()}\n\n"
            "**⭐ Start here if you are a beginner!**\n"
            f"> **Learning English?** — "
            f"{_channel_mention(BEGINNER_ENGLISH_CHANNEL_ID)}\n"
            f"> **Learning Spanish?** — "
            f"{_channel_mention(BEGINNER_SPANISH_CHANNEL_ID)}\n\n"
            "-# **New around here?** You'll need to wait 3 hours before "
            "you can join voice channels. If this is your first day on "
            "Discord, the wait is 24 hours."
        ),
        color=WELCOME_COLOR,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Spanish-English Learning Server")
    return embed


def build_spanish_dm_embed(member: discord.Member) -> discord.Embed:
    """Build the Spanish welcome DM embed."""
    embed = discord.Embed(
        title="Bienvenido/a",
        description=(
            "Bienvenido/a al servidor de aprendizaje de español e inglés.\n\n"
            "**・Roles**\n"
            f"Comienza por configurar tu perfil de aprendizaje mediante "
            f"{CUSTOMIZE_MENTION}.\n\n"
            "**・Navega por los siguientes canales para empezar a interactuar "
            "con la comunidad**\n"
            f"{_community_channel_lines()}\n\n"
            "**⭐ ¡Empieza desde aquí si eres principiante!**\n"
            f"> **¿Aprendes inglés?** — "
            f"{_channel_mention(BEGINNER_ENGLISH_CHANNEL_ID)}\n"
            f"> **¿Aprendes español?** — "
            f"{_channel_mention(BEGINNER_SPANISH_CHANNEL_ID)}\n\n"
            "-# **¿Eres nuevo/a por aquí?** Tendrás que esperar 3 horas "
            "antes de poder unirte a los canales de voz. Si es tu primer "
            "día en Discord, la espera será de 24 horas."
        ),
        color=WELCOME_COLOR,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Spanish-English Learning Server")
    return embed


def build_dm_embed(
    member: discord.Member,
    language: WelcomeLanguage,
) -> discord.Embed:
    """Build the welcome DM embed according to the selected language."""
    if language == "es":
        return build_spanish_dm_embed(member)

    return build_english_dm_embed(member)


def build_channel_summary(language: WelcomeLanguage) -> str:
    """Build the short public summary sent in the command channel."""
    welcome_channel = _channel_mention(WELCOME_CHANNEL_ID)
    rai = _user_mention(RAI_BOT_ID)

    if language == "es":
        return (
            "¡Bienvenido/a! Este es un servidor centrado en el aprendizaje "
            "de español e inglés. Revisa tus MD para más información, o "
            f"{welcome_channel} para ver el mensaje de {rai}."
        )

    return (
        "Welcome! This is a server focused on Spanish and English learning. "
        "Check your DMs for more information, or "
        f"{welcome_channel} for {rai}'s message."
    )


class WelcomeCog(BaseCog):
    """Staff-triggered welcome commands."""

    @commands.command(
        name="welcome",
        aliases=["bienvenido"],
        usage="<member>",
    )
    @staff_only()
    async def welcome(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
    ) -> None:
        """Send a staff-triggered welcome DM and a short channel summary."""
        if member is None:
            await ctx.send(
                embed=red_embed(
                    (
                        "You need to mention a member.\n\n"
                        f"Correct usage:\n"
                        f"`{ctx.prefix}{ctx.invoked_with} @member`"
                    ),
                    title="Missing member",
                )
            )
            return

        language = language_from_command(ctx.invoked_with)
        embed = build_dm_embed(member, language)

        try:
            await member.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(
                embed=red_embed(
                    (
                        f"I could not send a DM to {member.mention}.\n"
                        "They may have DMs disabled."
                    ),
                    title="DM failed",
                )
            )
            return
        except discord.HTTPException:
            logger.exception(
                "Failed to send welcome DM to user %s (%s)",
                member,
                member.id,
            )
            await ctx.send(
                embed=red_embed(
                    (
                        f"I could not send the welcome DM to {member.mention}. "
                        "Please try again later."
                    ),
                    title="DM failed",
                )
            )
            return

        await ctx.send(
            content=f"{member.mention}\n{build_channel_summary(language)}",
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )

        logger.info(
            "Welcome DM sent to user %s (%s) by %s (%s) in guild %s",
            member,
            member.id,
            ctx.author,
            ctx.author.id,
            ctx.guild.id if ctx.guild else "DM",
        )


async def setup(bot: commands.Bot) -> None:
    """Load the welcome cog."""
    await bot.add_cog(WelcomeCog(bot))
