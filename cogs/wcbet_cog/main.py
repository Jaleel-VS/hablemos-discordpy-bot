"""World Cup betting cog — `$wcbet` opens a personal ephemeral betting panel.

Group-stage match betting with virtual coins: opt in once for a starting
balance, pick today's match + outcome + stake from a Components V2
stepper, and get paid 1.5x on correct bets.

Results arrive via a polling task that watches ESPN's free scoreboard
endpoint while a match is in its post-kickoff window. By default it only
*proposes* the settlement command in the log channel; set
`WCBET_AUTO_SETTLE=1` to let it settle bets itself. Manual settlement via
the owner-only `$wcbetadmin` group (see `admin.py`) always works and
wins races safely (the result row insert is the duplicate guard).
"""
import logging
from datetime import UTC, datetime

import discord
from discord.ext import commands, tasks

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, green_embed
from db.bets import MatchAlreadySettledError

from . import betting, espn, results
from .betting import format_player_results
from .admin import WCBetAdmin
from .config import (
    WCBET_AUTO_SETTLE,
    WCBET_LOG_CHANNEL_ID,
    WCBET_NOTIFICATION_CHANNEL_ID,
    WCBET_RESULTS_POLL_MINUTES,
)
from .mod import WCBetMod
from .views import OpenBetPanelView

logger = logging.getLogger(__name__)


class WCBet(BaseCog):
    """`$wcbet` — World Cup match betting with virtual coins."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        # Matches already proposed in the log channel this process, so
        # propose mode does not repeat itself every poll.
        self._proposed: set[int] = set()
        self.poll_results.change_interval(minutes=WCBET_RESULTS_POLL_MINUTES)
        self.poll_results.start()

    async def cog_unload(self) -> None:
        self.poll_results.cancel()

    # ---------- commands ----------

    async def _send_prompt(self, ctx: commands.Context) -> None:
        """Send the public button prompt that opens a personal panel."""
        view = OpenBetPanelView(self.bot)
        prompt = await ctx.send(
            "🎰 **World Cup betting** — click to open your personal panel.",
            view=view,
        )
        view.prompt_message = prompt

    # Public entrypoint.
    @commands.command(name="wcbet")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def wcbet(self, ctx: commands.Context) -> None:
        """Open the World Cup betting panel."""
        await self._send_prompt(ctx)

    @commands.command(name="wcbettest")
    @commands.is_owner()
    @commands.guild_only()
    async def wcbettest(self, ctx: commands.Context) -> None:
        """Open the World Cup betting panel (owner-only test entrypoint)."""
        await self._send_prompt(ctx)

    @commands.command(name="wcbettop")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.guild_only()
    async def wcbettop(self, ctx: commands.Context) -> None:
        """Show the top 10 World Cup betting balances."""
        rows = await self.bot.db.get_wc_top_balances(ctx.guild.id)
        if not rows:
            await ctx.send(embed=blue_embed("No wallets yet."))
            return
        lines = [
            f"{i}. <@{r['user_id']}> — **{r['balance']:,}** coins"
            for i, r in enumerate(rows, 1)
        ]
        await ctx.send(embed=blue_embed("🏆 **WC Betting Leaderboard**\n" + "\n".join(lines)))

    # ---------- results polling ----------

    @tasks.loop(minutes=5)
    async def poll_results(self) -> None:
        """Poll ESPN for finished matches we have not settled yet."""
        try:
            await self._poll_results_once()
        except Exception:
            logger.exception("World Cup results poll failed")

    @poll_results.before_loop
    async def before_poll_results(self) -> None:
        await self.bot.wait_until_ready()

    async def _poll_results_once(self) -> None:
        now = datetime.now(UTC)
        settled = await self.bot.db.get_wc_settled_match_ids()
        awaiting = results.fixtures_awaiting_result(now, settled)
        if not awaiting:
            return
        # ESPN's `dates` param is the ET calendar date — same convention
        # as our fixture rows, so the fixture date strings are reusable.
        for date_str in sorted({f["date"].replace("-", "") for f in awaiting}):
            payload = await espn.fetch_scoreboard(date_str)
            if payload is None:
                continue
            for result in results.match_results(payload, awaiting):
                await self._handle_result(result)

    async def _handle_result(self, result: results.MatchResult) -> None:
        """Settle or propose a finished match, depending on the mode flag."""
        match_id = result["match_id"]
        home_score, away_score = result["home_score"], result["away_score"]
        fixture = next(
            (f for f in betting.GROUP_STAGE_FIXTURES if f["match_id"] == match_id), None,
        )
        if fixture is None:
            return
        label = f"{fixture['home']} {home_score}–{away_score} {fixture['away']}"

        if not WCBET_AUTO_SETTLE:
            if match_id in self._proposed:
                return
            self._proposed.add(match_id)
            await self._announce(
                f"🏁 **Match #{match_id} finished:** {label}\n"
                f"Settle with `$wcbetadmin result {match_id} {home_score}-{away_score}`",
            )
            return

        outcome = betting.outcome_from_score(home_score, away_score)
        try:
            summary = await self.bot.db.settle_wc_match(
                match_id, home_score, away_score, outcome, payout_fn=betting.payout,
            )
        except MatchAlreadySettledError:
            return  # manual settlement won the race — nothing to do
        logger.info(
            "Auto-settled match %s (%s): %s won, %s lost, %s coins paid",
            match_id, label, summary["winners"], summary["losers"], summary["total_paid"],
        )
        await self._announce(
            embed=green_embed(
                f"🏁 **Match settled automatically** — {label}\n"
                f"✅ {summary['winners']} won · ❌ {summary['losers']} lost · "
                f"💰 {summary['total_paid']:,} coins paid",
            ),
        )
        player_msg = format_player_results(summary.get("bets", []))
        if player_msg:
            await self._announce(player_msg, channel_id=WCBET_NOTIFICATION_CHANNEL_ID)

    async def _announce(self, content: str | None = None, *, embed=None, channel_id: int = WCBET_LOG_CHANNEL_ID) -> None:
        """Post to a World Cup channel, tolerating a missing channel."""
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            logger.warning("World Cup channel %s not found", channel_id)
            return
        try:
            await channel.send(content=content, embed=embed)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.error("Failed to post to channel %s: %s", channel_id, exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WCBet(bot))
    await bot.add_cog(WCBetAdmin(bot))
    await bot.add_cog(WCBetMod(bot))
