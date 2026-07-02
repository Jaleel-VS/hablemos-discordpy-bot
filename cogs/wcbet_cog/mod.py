"""Moderator commands for the World Cup betting cog.

`manage_messages`-gated prefix group `$wcbetmod` — a tier below the
owner-only `$wcbetadmin` (which owns match-wide settlement). Mods get
per-user tools: inspect a wallet, ban/unban a user from betting, and
adjust a balance. Balance adjustments require an explicit confirmation
and are logged loudly to the shared World Cup channel.

Match results and match-wide voids stay owner-only (`admin.py`) — they
move everyone's coins at once.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, green_embed, red_embed, yellow_embed

from .config import WCBET_LOG_CHANNEL_ID

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

# Guard against fat-fingered grants minting absurd balances.
MAX_ADJUSTMENT = 1_000_000


def _resolve_member(ctx: commands.Context, target: str | None) -> discord.Member | None:
    """Resolve a member from a mention or raw user ID."""
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
        return member if isinstance(member, discord.Member) else None
    if target is None:
        return None
    raw = target.strip().lstrip("<@!").rstrip(">")
    if not raw.isdigit() or ctx.guild is None:
        return None
    return ctx.guild.get_member(int(raw))


class WCBetMod(BaseCog):
    """Moderator-only `$wcbetmod` group (`manage_messages`)."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)

    @commands.group(name="wcbetmod", invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def wcbetmod(self, ctx: commands.Context) -> None:
        """Moderator tools for World Cup betting."""
        await ctx.send(
            embed=blue_embed(
                "Usage: `$wcbetmod <user|ban|unban|give|take> [@user] [args]`",
            ),
        )

    # ---------- inspect ----------

    @wcbetmod.command(name="user")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def user(self, ctx: commands.Context, *, target: str | None = None) -> None:
        """Show a user's wallet, pending bets, and lifetime tallies."""
        member = _resolve_member(ctx, target)
        if member is None:
            await ctx.send(embed=red_embed("Usage: `$wcbetmod user <@user|user_id>`"))
            return

        summary = await self.bot.db.get_wc_user_summary(member.id)
        if summary is None:
            await ctx.send(
                embed=blue_embed(f"{member.mention} has no betting wallet."),
            )
            return

        banned = await self.bot.db.is_wc_bet_banned(member.id)
        embed = discord.Embed(
            title=f"World Cup betting — {member.display_name}",
            color=discord.Color.red() if banned else discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Balance", value=f"{summary['balance']:,}", inline=True)
        embed.add_field(
            name="Pending",
            value=f"{summary['pending']} ({summary['pending_stake']:,} staked)",
            inline=True,
        )
        embed.add_field(
            name="Record",
            value=(
                f"✅ {summary['won']} won ({summary['won_payout']:,} paid)\n"
                f"❌ {summary['lost']} lost · ↩️ {summary['void']} void"
            ),
            inline=False,
        )
        if banned:
            embed.add_field(name="Status", value="🚫 Banned from betting", inline=False)
        await ctx.send(embed=embed)

    # ---------- ban / unban ----------

    @wcbetmod.command(name="ban")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, target: str, *, reason: str | None = None) -> None:
        """Ban a user from opening the betting panel."""
        member = _resolve_member(ctx, target)
        if member is None:
            await ctx.send(embed=red_embed("Usage: `$wcbetmod ban <@user|user_id> [reason]`"))
            return
        if ctx.guild is None:
            return

        await self.bot.db.set_wc_bet_ban(
            member.id, ctx.guild.id, ctx.author.id, reason,
        )
        await ctx.send(
            embed=green_embed(f"🚫 Banned {member.mention} from World Cup betting."),
        )
        logger.info(
            "wcbetmod: %s banned %s from betting (reason=%s)",
            ctx.author, member.id, reason,
        )
        await self._log_mod_action(
            ctx.guild,
            title="🚫 Betting ban",
            description=(
                f"{member.mention} was banned from betting by {ctx.author.mention}."
                + (f"\n**Reason:** {reason}" if reason else "")
            ),
            color=discord.Color.red(),
        )

    @wcbetmod.command(name="unban")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, *, target: str | None = None) -> None:
        """Lift a user's betting ban."""
        member = _resolve_member(ctx, target)
        if member is None:
            await ctx.send(embed=red_embed("Usage: `$wcbetmod unban <@user|user_id>`"))
            return
        if ctx.guild is None:
            return

        removed = await self.bot.db.remove_wc_bet_ban(member.id)
        if not removed:
            await ctx.send(embed=blue_embed(f"{member.mention} wasn't banned."))
            return
        await ctx.send(
            embed=green_embed(f"✅ Unbanned {member.mention} from World Cup betting."),
        )
        logger.info("wcbetmod: %s unbanned %s", ctx.author, member.id)
        await self._log_mod_action(
            ctx.guild,
            title="✅ Betting unban",
            description=f"{member.mention} was unbanned by {ctx.author.mention}.",
            color=discord.Color.green(),
        )

    # ---------- balance adjustment ----------

    @wcbetmod.command(name="give")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def give(self, ctx: commands.Context, target: str, amount: int) -> None:
        """Grant coins to a user's wallet (with confirmation)."""
        await self._adjust(ctx, target, amount)

    @wcbetmod.command(name="take")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def take(self, ctx: commands.Context, target: str, amount: int) -> None:
        """Deduct coins from a user's wallet (with confirmation)."""
        await self._adjust(ctx, target, -amount)

    async def _adjust(self, ctx: commands.Context, target: str, delta: int) -> None:
        """Shared give/take path: validate, confirm, apply, log."""
        member = _resolve_member(ctx, target)
        if member is None:
            await ctx.send(embed=red_embed("Usage: `$wcbetmod <give|take> <@user|user_id> <amount>`"))
            return
        if ctx.guild is None:
            return
        if delta == 0 or abs(delta) > MAX_ADJUSTMENT:
            await ctx.send(
                embed=red_embed(
                    f"Amount must be between 1 and {MAX_ADJUSTMENT:,}.",
                ),
            )
            return

        summary = await self.bot.db.get_wc_user_summary(member.id)
        if summary is None:
            await ctx.send(embed=red_embed(f"{member.mention} has no betting wallet."))
            return

        verb = "grant" if delta > 0 else "deduct"
        projected = max(0, summary["balance"] + delta)
        confirmed = await self._confirm(
            ctx,
            f"⚠️ {verb.capitalize()} **{abs(delta):,}** coins "
            f"{'to' if delta > 0 else 'from'} {member.mention}? "
            f"Balance: **{summary['balance']:,} → {projected:,}**.",
        )
        if not confirmed:
            await ctx.send(embed=yellow_embed("Cancelled."))
            return

        new_balance = await self.bot.db.adjust_wc_balance(member.id, delta)
        if new_balance is None:
            await ctx.send(embed=red_embed(f"{member.mention} has no betting wallet."))
            return

        await ctx.send(
            embed=green_embed(
                f"Adjusted {member.mention}'s balance by **{delta:+,}** "
                f"→ **{new_balance:,}** coins.",
            ),
        )
        logger.info(
            "wcbetmod: %s adjusted %s balance by %+d -> %d",
            ctx.author, member.id, delta, new_balance,
        )
        await self._log_mod_action(
            ctx.guild,
            title="💰 Balance adjustment",
            description=(
                f"{ctx.author.mention} adjusted {member.mention}'s balance by "
                f"**{delta:+,}** → **{new_balance:,}** coins."
            ),
            color=discord.Color.orange(),
        )

    async def _confirm(self, ctx: commands.Context, prompt: str) -> bool:
        """Yes/no reaction confirmation. Returns False on timeout."""
        message = await ctx.send(embed=yellow_embed(prompt + "\n\nReact ✅ to confirm."))
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                user.id == ctx.author.id
                and reaction.message.id == message.id
                and str(reaction.emoji) in {"✅", "❌"}
            )

        try:
            reaction, _ = await self.bot.wait_for(
                "reaction_add", timeout=30.0, check=check,
            )
        except TimeoutError:
            return False
        return str(reaction.emoji) == "✅"

    # ---------- helpers ----------

    async def _log_mod_action(
        self,
        guild: discord.Guild,
        *,
        title: str,
        description: str,
        color: discord.Color,
    ) -> None:
        """Send a mod-action embed to the shared World Cup log channel."""
        channel = guild.get_channel(WCBET_LOG_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "wcbetmod log channel %s not found in guild %s",
                WCBET_LOG_CHANNEL_ID, guild.id,
            )
            return
        embed = discord.Embed(title=title, description=description, color=color)
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.error(
                "Failed to send mod-action log to channel %s: %s",
                WCBET_LOG_CHANNEL_ID, exc,
            )
