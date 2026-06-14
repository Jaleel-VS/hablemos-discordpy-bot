"""Admin commands for the World Cup betting cog.

Owner-only prefix command group `$wcbetadmin` — record match results
(which settles all pending bets atomically), void postponed matches,
and view participation stats.
"""
import logging

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, green_embed, red_embed
from cogs.wcpredict_cog.fixtures import FIXTURE_BY_ID, Fixture
from db.bets import MatchAlreadySettledError

from . import betting, espn, results
from .betting import format_parlay_results, format_player_results
from .config import WCBET_LOG_CHANNEL_ID, WCBET_NOTIFICATION_CHANNEL_ID

logger = logging.getLogger(__name__)


class WCBetAdmin(BaseCog):
    """Owner-only `$wcbetadmin` admin group."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    @commands.group(name="wcbetadmin", invoke_without_command=True)
    @commands.is_owner()
    async def wcbetadmin(self, ctx: commands.Context) -> None:
        """Admin tools for the World Cup betting feature."""
        await ctx.send("Usage: `$wcbetadmin <result|void|stats>`")

    # ---------- result ----------

    @wcbetadmin.command(name="result")
    @commands.is_owner()
    async def result(self, ctx: commands.Context, match_id: int, *, score: str | None = None) -> None:
        """Record a final score and settle all pending bets on the match.

        Omit score to auto-fetch from ESPN.
        Examples:
            $wcbetadmin result 1
            $wcbetadmin result 1 2-1
        """
        if ctx.guild is None:
            await ctx.send(embed=red_embed("Run this in the league guild."))
            return

        fixture = self._group_stage_fixture(match_id)
        if fixture is None:
            await ctx.send(
                embed=red_embed(f"Match `{match_id}` is not a known group-stage fixture."),
            )
            return

        if score is None:
            date_str = fixture["date"].replace("-", "")
            payload = await espn.fetch_scoreboard(date_str)
            if payload is None:
                await ctx.send(embed=red_embed("ESPN fetch failed — provide the score manually."))
                return
            matches = results.match_results(payload, [fixture])
            if not matches:
                await ctx.send(
                    embed=red_embed(
                        f"Match `{match_id}` not found or not completed on ESPN yet. "
                        "Provide the score manually."
                    )
                )
                return
            home_score, away_score = matches[0]["home_score"], matches[0]["away_score"]
        else:
            parsed = betting.parse_score(score)
            if parsed is None:
                await ctx.send(
                    embed=red_embed("Couldn't parse that score. Use `<home>-<away>`, e.g. `2-1`."),
                )
                return
            home_score, away_score = parsed

        outcome = betting.outcome_from_score(home_score, away_score)

        try:
            summary = await self.bot.db.settle_wc_match(
                match_id, home_score, away_score, outcome, payout_fn=betting.payout,
            )
        except MatchAlreadySettledError:
            await ctx.send(embed=red_embed(f"Match `{match_id}` was already settled."))
            return

        line = (
            f"✅ **{fixture['home']} {home_score}–{away_score} {fixture['away']}** "
            f"({outcome}): {summary['winners']} won / {summary['losers']} lost / "
            f"**{summary['total_paid']:,}** coins paid."
        )
        await ctx.send(embed=green_embed(line))
        logger.info(
            "wcbet: match %s settled %s-%s (%s) by %s — %s winners, %s losers, %s paid",
            match_id, home_score, away_score, outcome, ctx.author,
            summary["winners"], summary["losers"], summary["total_paid"],
        )
        await self._log_settlement(ctx.guild, fixture, home_score, away_score, summary)

    # ---------- void ----------

    @wcbetadmin.command(name="void")
    @commands.is_owner()
    async def void(self, ctx: commands.Context, match_id: int) -> None:
        """Refund all pending stakes on a match (postponement)."""
        if ctx.guild is None:
            await ctx.send(embed=red_embed("Run this in the league guild."))
            return

        fixture = self._group_stage_fixture(match_id)
        if fixture is None:
            await ctx.send(
                embed=red_embed(f"Match `{match_id}` is not a known group-stage fixture."),
            )
            return

        summary = await self.bot.db.void_wc_match(match_id)
        await ctx.send(
            embed=green_embed(
                f"↩️ Match `{match_id}` voided: {summary['refunded']} bet(s) refunded, "
                f"**{summary['total_refunded']:,}** coins returned.",
            ),
        )
        logger.info(
            "wcbet: match %s voided by %s — %s bets, %s coins refunded",
            match_id, ctx.author, summary["refunded"], summary["total_refunded"],
        )

    # ---------- stats ----------

    @wcbetadmin.command(name="pending")
    @commands.is_owner()
    async def pending(self, ctx: commands.Context) -> None:
        """List matches with pending bets that have no result recorded yet."""
        rows = await self.bot.db.get_wc_pending_unsettled()
        if not rows:
            await ctx.send(embed=green_embed("No pending unsettled bets."))
            return
        lines = [
            f"Match **{r['match_id']}** — {r['bet_count']} bet(s), {int(r['total_staked']):,} staked"
            for r in rows
        ]
        await ctx.send(embed=blue_embed("**Pending unsettled bets:**\n" + "\n".join(lines)))

    @wcbetadmin.command(name="history")
    @commands.is_owner()
    async def history(self, ctx: commands.Context, user: discord.Member) -> None:
        """Show the last 15 balance events for a user."""
        rows = await self.bot.db.get_wc_balance_history(user.id)
        if not rows:
            await ctx.send(embed=blue_embed(f"No balance history for {user.display_name}."))
            return
        lines = [
            f"`{r['created_at'].strftime('%m-%d %H:%M')}` "
            f"{r['delta']:+d} → **{r['balance']:,}** `{r['event']}`"
            + (f" match {r['match_id']}" if r['match_id'] else "")
            for r in rows
        ]
        await ctx.send(embed=blue_embed(f"**{user.display_name} balance history:**\n" + "\n".join(lines)))

    @wcbetadmin.command(name="stats")
    @commands.is_owner()
    async def stats(self, ctx: commands.Context) -> None:
        """Show wallet count, pending bets, total staked, top balance."""
        if ctx.guild is None:
            await ctx.send(embed=red_embed("Run this in the league guild."))
            return

        stats = await self.bot.db.wc_bet_stats(ctx.guild.id)
        top = stats["top_balance"]
        top_line = f"{top:,}" if top is not None else "—"
        await ctx.send(
            embed=blue_embed(
                f"**Wallets:** {stats['wallets']}\n"
                f"**Pending bets:** {stats['pending_bets']}\n"
                f"**Total staked:** {stats['total_staked']:,}\n"
                f"**Top balance:** {top_line}",
            ),
        )

    # ---------- helpers ----------

    @staticmethod
    def _group_stage_fixture(match_id: int) -> Fixture | None:
        """Return the fixture if it exists and is a group-stage match."""
        fixture = FIXTURE_BY_ID.get(match_id)
        if fixture is None or fixture["group"] is None:
            return None
        return fixture

    async def _log_settlement(
        self,
        guild: discord.Guild,
        fixture: Fixture,
        home_score: int,
        away_score: int,
        summary: dict,
    ) -> None:
        channel = guild.get_channel(WCBET_LOG_CHANNEL_ID)
        if channel is None:
            logger.warning(
                "wcbet log channel %s not found in guild %s",
                WCBET_LOG_CHANNEL_ID, guild.id,
            )
            return
        embed = discord.Embed(
            title="🏁 Match settled",
            description=(
                f"**{fixture['home']} {home_score}–{away_score} {fixture['away']}** "
                f"(match {fixture['match_id']})\n"
                f"{summary['winners']} won / {summary['losers']} lost — "
                f"**{summary['total_paid']:,}** coins paid out."
            ),
            color=discord.Color.gold(),
        )
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.error(
                "Failed to send settlement log to channel %s: %s",
                WCBET_LOG_CHANNEL_ID, exc,
            )
        player_msg = format_player_results(
            summary.get("bets", []),
            label=f"{fixture['home']} {home_score}–{away_score} {fixture['away']}",
        )
        parlay_msg = format_parlay_results(summary.get("parlays", []))
        if player_msg or parlay_msg:
            notify = guild.get_channel(WCBET_NOTIFICATION_CHANNEL_ID)
            if notify is None:
                logger.warning("wcbet notification channel %s not found", WCBET_NOTIFICATION_CHANNEL_ID)
                return
            for msg in (player_msg, parlay_msg):
                if not msg:
                    continue
                try:
                    await notify.send(msg)
                except (discord.Forbidden, discord.HTTPException) as exc:
                    logger.error(
                        "Failed to post results to channel %s: %s",
                        WCBET_NOTIFICATION_CHANNEL_ID, exc,
                    )
