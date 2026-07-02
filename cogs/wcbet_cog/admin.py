"""Admin commands for the World Cup betting cog.

Owner-only prefix command group `$wcbetadmin` — record match results
(which settles all pending bets atomically), void postponed matches,
and view participation stats.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, green_embed, red_embed
from cogs.wcpredict_cog.fixtures import (
    FIXTURE_BY_ID,
    Fixture,
    apply_fixture_override,
    is_fixture_resolved,
)
from db.bets import MatchAlreadySettledError

from . import betting, espn, results
from .betting import format_parlay_results, format_player_results
from .config import WCBET_LOG_CHANNEL_ID, WCBET_NOTIFICATION_CHANNEL_ID

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

# Parses a `$wcbetadmin setteam` pairing: "<home> vs <away>" with an
# optional trailing "@ HH:MM" ET kickoff. "vs" is matched case-insensitively
# as a whole word so team names containing 's'/'v' are unaffected. Time is
# 24-hour HH:MM. Team names may contain spaces, accents, and apostrophes.
_SETTEAM_RE = re.compile(
    r"^\s*(?P<home>.+?)\s+vs\s+(?P<away>.+?)\s*(?:@\s*(?P<time>\d{1,2}:\d{2}))?\s*$",
    re.IGNORECASE,
)


def _parse_setteam(text: str) -> tuple[str, str, str | None] | None:
    """Parse "<home> vs <away> [@ HH:MM]" into (home, away, time_et|None).

    Returns None when the input doesn't contain a " vs " separator or both
    team names aren't present. The kickoff is validated as 00:00–23:59.
    """
    match = _SETTEAM_RE.match(text)
    if match is None:
        return None
    home = match.group("home").strip()
    away = match.group("away").strip()
    if not home or not away:
        return None
    time_et = match.group("time")
    if time_et is not None:
        hours, minutes = (int(part) for part in time_et.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            return None
        time_et = f"{hours:02d}:{minutes:02d}"
    return home, away, time_et


_RESULT_PENS_RE = re.compile(
    r"\s+(?:pens?|penalties)\s*[:\s]\s*(?P<side>home|away)\s*$",
    re.IGNORECASE,
)


def _parse_result_arg(text: str) -> tuple[str, betting.Outcome | None]:
    """Split a result argument into (score_part, penalty_winner|None).

    Accepts an optional trailing shootout marker naming the side that
    advanced on a level knockout score, e.g. ``"1-1 pens home"`` ->
    ``("1-1", "home")``. With no marker, returns ``(text, None)``. The
    score itself is validated later by ``betting.parse_score``.
    """
    match = _RESULT_PENS_RE.search(text)
    if match is None:
        return text.strip(), None
    side: betting.Outcome = "home" if match.group("side").lower() == "home" else "away"
    score_part = text[: match.start()].strip()
    return score_part, side


class WCBetAdmin(BaseCog):
    """Owner-only `$wcbetadmin` admin group."""

    # Bounds for the house odds multiplier (`$wcbetadmin multiplier`).
    _MULTIPLIER_MIN = Decimal("0.5")
    _MULTIPLIER_MAX = Decimal("10")

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)

    @commands.group(name="wcbetadmin", invoke_without_command=True)
    @commands.is_owner()
    async def wcbetadmin(self, ctx: commands.Context) -> None:
        """Admin tools for the World Cup betting feature."""
        await ctx.send("Usage: `$wcbetadmin <result|void|stats|multiplier>`")

    # ---------- result ----------

    @wcbetadmin.command(name="result")
    @commands.is_owner()
    async def result(self, ctx: commands.Context, match_id: int, *, score: str | None = None) -> None:
        """Record a final score and settle all pending bets on the match.

        Omit score to auto-fetch from ESPN.
        Knockout shootouts: on a level score, name the side that advanced
        with a trailing `pens home` / `pens away`.
        Examples:
            $wcbetadmin result 1
            $wcbetadmin result 1 2-1
            $wcbetadmin result 73 1-1 pens home
        """
        if ctx.guild is None:
            await ctx.send(embed=red_embed("Run this in the league guild."))
            return

        fixture = self._settleable_fixture(match_id)
        if fixture is None:
            await ctx.send(
                embed=red_embed(
                    f"Match `{match_id}` is unknown or its knockout teams "
                    "aren't resolved yet — set them with `$wcbetadmin setteam`."
                ),
            )
            return

        winner: betting.Outcome | None = None
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
            winner = matches[0].get("winner")
        else:
            # Knockout shootouts: allow a trailing `pens <home|away>` to name
            # the side that advanced on a level score, e.g. `1-1 pens home`.
            score_part, winner = _parse_result_arg(score)
            parsed = betting.parse_score(score_part)
            if parsed is None:
                await ctx.send(
                    embed=red_embed(
                        "Couldn't parse that score. Use `<home>-<away>`, e.g. `2-1` "
                        "(knockout shootout: add `pens home` or `pens away`)."
                    ),
                )
                return
            home_score, away_score = parsed

        outcome = betting.settle_outcome(fixture, home_score, away_score, winner=winner)
        if outcome is None:
            await ctx.send(
                embed=red_embed(
                    f"**{fixture['home']} {home_score}–{away_score} {fixture['away']}** "
                    "is a knockout that ended level — name the side that advanced "
                    f"on penalties: `$wcbetadmin result {match_id} {home_score}-"
                    f"{away_score} pens home` (or `pens away`)."
                ),
            )
            return

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

    @wcbetadmin.command(name="multiplier")
    @commands.is_owner()
    async def multiplier(
        self, ctx: commands.Context, value: str | None = None,
    ) -> None:
        """Show or set the house odds multiplier applied to all offered lines.

        Affects only NEW bets — already-placed bets keep their snapshotted
        odds. Boosts both real ESPN lines and the flat fallback.
        Examples:
            $wcbetadmin multiplier        → show current
            $wcbetadmin multiplier 1.5    → juice all odds by 1.5x
            $wcbetadmin multiplier 1      → reset to no boost
        """
        if value is None:
            current = await self.bot.db.get_wc_odds_multiplier()
            await ctx.send(
                embed=blue_embed(
                    f"Current odds multiplier: **{current}x**\n"
                    "Set with `$wcbetadmin multiplier <value>` "
                    f"(allowed range {self._MULTIPLIER_MIN}–{self._MULTIPLIER_MAX}).",
                ),
            )
            return

        try:
            parsed = Decimal(value).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            await ctx.send(
                embed=red_embed("Couldn't parse that — give a number like `1.5`."),
            )
            return

        if not self._MULTIPLIER_MIN <= parsed <= self._MULTIPLIER_MAX:
            await ctx.send(
                embed=red_embed(
                    f"Multiplier must be between {self._MULTIPLIER_MIN} and "
                    f"{self._MULTIPLIER_MAX}.",
                ),
            )
            return

        await self.bot.db.set_wc_odds_multiplier(parsed)
        await ctx.send(
            embed=green_embed(
                f"🎲 Odds multiplier set to **{parsed}x**. "
                "Applies to new bets from now on (existing bets keep their "
                "locked-in odds).",
            ),
        )
        logger.info("wcbet: odds multiplier set to %s by %s", parsed, ctx.author)

    # ---------- knockout team resolution ----------

    @wcbetadmin.command(name="setteam")
    @commands.is_owner()
    async def setteam(
        self, ctx: commands.Context, match_id: int, *, teams: str | None = None,
    ) -> None:
        """Resolve a knockout fixture's real teams (and optionally kickoff).

        Knockout fixtures ship with bracket placeholders ("Winner Group A")
        and aren't bettable or settleable until their teams are filled in.
        This writes the real pairing, applies it immediately (no redeploy),
        and persists it so it survives restarts. Use exact team names as
        they appear in the group standings (e.g. "USA", "Côte d'Ivoire").

        Format: `<home> vs <away>` (the literal word "vs" separates sides),
        with an optional `@ HH:MM` ET kickoff override appended.

        Examples:
            $wcbetadmin setteam 73 Mexico vs Brazil
            $wcbetadmin setteam 89 Spain vs France @ 16:00
        """
        fixture = FIXTURE_BY_ID.get(match_id)
        if fixture is None:
            await ctx.send(embed=red_embed(f"Match `{match_id}` is not a known fixture."))
            return
        if fixture["group"] is not None:
            await ctx.send(
                embed=red_embed(
                    f"Match `{match_id}` is a group-stage fixture with fixed "
                    "teams — setteam is only for knockout pairings."
                ),
            )
            return
        if teams is None:
            await ctx.send(
                embed=red_embed(
                    "Give the pairing as `<home> vs <away>`, e.g. "
                    "`$wcbetadmin setteam 73 Mexico vs Brazil`."
                ),
            )
            return

        parsed = _parse_setteam(teams)
        if parsed is None:
            await ctx.send(
                embed=red_embed(
                    "Couldn't parse that. Use `<home> vs <away>` (optionally "
                    "`@ HH:MM`), e.g. `Spain vs France @ 16:00`."
                ),
            )
            return
        home, away, time_et = parsed

        await self.bot.db.set_wc_fixture_override(match_id, home, away, time_et)
        apply_fixture_override(match_id, home, away, time_et)

        when = f" · kickoff {time_et} ET" if time_et else ""
        await ctx.send(
            embed=green_embed(
                f"🏟️ Match `{match_id}` set to **{home} vs {away}**{when}. "
                "It's now bettable once inside the 24h window."
            ),
        )
        logger.info(
            "wcbet: match %s teams set to %s vs %s (time %s) by %s",
            match_id, home, away, time_et or "unchanged", ctx.author,
        )

    # ---------- void ----------

    @wcbetadmin.command(name="void")
    @commands.is_owner()
    async def void(self, ctx: commands.Context, match_id: int) -> None:
        """Refund all pending stakes on a match (postponement)."""
        if ctx.guild is None:
            await ctx.send(embed=red_embed("Run this in the league guild."))
            return

        fixture = self._settleable_fixture(match_id)
        if fixture is None:
            await ctx.send(
                embed=red_embed(
                    f"Match `{match_id}` is unknown or its knockout teams "
                    "aren't resolved yet — set them with `$wcbetadmin setteam`."
                ),
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
    def _settleable_fixture(match_id: int) -> Fixture | None:
        """Return the fixture if it exists and has real (resolved) teams.

        Group-stage fixtures are always resolved. Knockout fixtures are
        settleable only once their teams have been filled in via
        `$wcbetadmin setteam` (otherwise both sides are bracket
        placeholders and there is no ESPN event to match).
        """
        fixture = FIXTURE_BY_ID.get(match_id)
        if fixture is None or not is_fixture_resolved(fixture):
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
        if not isinstance(channel, discord.abc.Messageable):
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
            if not isinstance(notify, discord.abc.Messageable):
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
