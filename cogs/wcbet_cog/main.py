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
from decimal import Decimal

import discord
from discord import ui
from discord.ext import commands, tasks

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, green_embed
from cogs.utils.names import resolve_member_labels
from cogs.wcpredict_cog.fixtures import FIXTURE_BY_ID, apply_fixture_overrides
from cogs.wcpredict_cog.fixtures_view import TEAM_FLAGS
from db.bets import MatchAlreadySettledError

from . import betting, espn, results
from .admin import WCBetAdmin
from .betting import format_parlay_results, format_player_results
from .config import (
    WCBET_AUTO_SETTLE,
    WCBET_LOG_CHANNEL_ID,
    WCBET_NOTIFICATION_CHANNEL_ID,
    WCBET_ODDS,
    WCBET_RESULTS_POLL_MINUTES,
)
from .mod import WCBetMod
from .views import OpenBetPanelView

logger = logging.getLogger(__name__)

BOARD_PAGE_SIZE = 4
HISTORY_PAGE_SIZE = 12

EVENT_LABELS = {
    'daily_allowance': 'Daily allowance',
    'bet_placed': 'Bet placed',
    'bet_won': 'Bet won',
    'bet_refund': 'Bet void/refund',
    'bet_cancel': 'Bet cancelled',
    'parlay_placed': 'Parlay placed',
    'parlay_won': 'Parlay won',
    'parlay_refund': 'Parlay refund',
    'parlay_cancel': 'Parlay cancelled',
}

OUTCOME_ORDER = ('home', 'draw', 'away')


def _fallback_board_odds(multiplier: Decimal = Decimal(1)) -> dict[str, Decimal]:
    """Flat fallback odds for board rendering, scaled by the house multiplier."""
    boosted = (WCBET_ODDS * multiplier).quantize(Decimal('0.01'))
    return {'home': boosted, 'draw': boosted, 'away': boosted}


def _build_profile_embed(member: discord.Member, p: dict) -> discord.Embed:
    """Render a betting profile dict into a stats card embed."""
    settled = p["wins"] + p["losses"]
    win_rate = f"{round(100 * p['wins'] / settled)}%" if settled else "—"
    net = p["total_won"] - p["settled_staked"]
    rank = f" (#{p['rank']})" if p["rank"] else ""
    streak = betting.current_streak(p["recent_settled"])

    embed = discord.Embed(
        title=f"📊 {member.display_name}'s betting profile",
        color=discord.Color.blurple(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="💰 Balance", value=f"{p['balance']:,}{rank}", inline=True)
    embed.add_field(name="📈 Net profit", value=f"{net:+,}", inline=True)
    embed.add_field(
        name="🎯 Record",
        value=f"{p['wins']}W · {p['losses']}L ({win_rate})",
        inline=True,
    )
    if p["pending"]:
        embed.add_field(
            name="🎟️ Pending",
            value=f"{p['pending']} bet(s) · {p['pending_staked']:,} staked",
            inline=True,
        )
    if p["biggest_win"]:
        embed.add_field(name="🏆 Biggest win", value=f"{p['biggest_win']:,}", inline=True)
    if p["longest_odds_won"]:
        embed.add_field(
            name="🐎 Longest odds won",
            value=f"{p['longest_odds_won']}x",
            inline=True,
        )
    if streak is not None:
        status, count = streak
        if count >= 2:
            emoji = "🔥" if status == "won" else "🥶"
            word = "win" if status == "won" else "loss"
            embed.set_footer(text=f"{emoji} {count}-{word} streak")
    return embed


def _team_label(name: str) -> str:
    """Return 'FLAG Name' for known teams, or just 'Name' otherwise."""
    flag = TEAM_FLAGS.get(name, "")
    return f"{flag} {name}".strip()


def _market_row(board: dict[str, dict[str, int]], outcome: str) -> tuple[int, int]:
    """Return (bettors, staked) for one outcome from a board row."""
    row = board.get(outcome, {})
    return int(row.get('bettors', 0)), int(row.get('staked', 0))


def _history_event_label(event: str) -> str:
    """Friendly label for a balance log event key."""
    return EVENT_LABELS.get(event, event.replace('_', ' ').title())


def _history_line(entry: dict) -> str:
    """Render one balance-log entry as a compact line."""
    ts = int(entry['created_at'].timestamp())
    delta = int(entry['delta'])
    sign = '+' if delta > 0 else ''
    match_suffix = f" · match {entry['match_id']}" if entry['match_id'] is not None else ''
    return (
        f"• **{_history_event_label(entry['event'])}** {sign}{delta:,}"
        f" → balance **{entry['balance']:,}**{match_suffix} [<t:{ts}:R>]"
    )


def _build_history_page(member: discord.Member, history: list[dict], page: int) -> ui.LayoutView:
    """Build a Components V2 history view for one page of balance events."""
    total_pages = max(1, (len(history) + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * HISTORY_PAGE_SIZE
    end = start + HISTORY_PAGE_SIZE
    rows = history[start:end]
    body = "\n".join(_history_line(row) for row in rows) if rows else "No balance events yet."

    view = ui.LayoutView(timeout=300)
    children: list[ui.Item] = [
        ui.TextDisplay(f"## 📜 {member.display_name}'s betting history"),
        ui.TextDisplay(body),
    ]

    if total_pages > 1:
        prev_btn = ui.Button(label='◀', style=discord.ButtonStyle.secondary, disabled=safe_page <= 0)
        next_btn = ui.Button(
            label='▶', style=discord.ButtonStyle.secondary, disabled=safe_page >= total_pages - 1,
        )

        async def prev_cb(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(view=_build_history_page(member, history, safe_page - 1))

        async def next_cb(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(view=_build_history_page(member, history, safe_page + 1))

        prev_btn.callback = prev_cb
        next_btn.callback = next_cb
        children.extend([
            ui.Separator(),
            ui.ActionRow(prev_btn, next_btn),
            ui.TextDisplay(f"-# Page {safe_page + 1}/{total_pages}"),
        ])

    view.add_item(ui.Container(*children, accent_colour=discord.Color.blurple()))
    return view


def _build_board_page(fixtures: list[dict], page: int) -> ui.LayoutView:
    """Build a Components V2 market board page for current bettable fixtures."""
    total_pages = max(1, (len(fixtures) + BOARD_PAGE_SIZE - 1) // BOARD_PAGE_SIZE)
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * BOARD_PAGE_SIZE
    end = start + BOARD_PAGE_SIZE

    view = ui.LayoutView(timeout=300)
    children: list[ui.Item] = [ui.TextDisplay("## 🎰 WC betting board")]

    page_rows = fixtures[start:end]
    if not page_rows:
        children.append(ui.TextDisplay("No current bettable matches."))
    else:
        blocks: list[str] = []
        for row in page_rows:
            fixture = row['fixture']
            odds = row['odds']
            board = row['board']
            ts = int(betting.kickoff_utc(fixture).timestamp())
            home_bettors, home_staked = _market_row(board, 'home')
            draw_bettors, draw_staked = _market_row(board, 'draw')
            away_bettors, away_staked = _market_row(board, 'away')
            total_pool = home_staked + draw_staked + away_staked
            blocks.append(
                "\n".join([
                    f"### {_team_label(fixture['home'])} vs {_team_label(fixture['away'])}",
                    f"-# kickoff <t:{ts}:f> [<t:{ts}:R>] · odds {odds['home']} / {odds['draw']} / {odds['away']}",
                    f"🏠 {_team_label(fixture['home'])}: **{home_staked:,}** coins · {home_bettors} bettor(s)",
                    f"🤝 Draw: **{draw_staked:,}** coins · {draw_bettors} bettor(s)",
                    f"✈️ {_team_label(fixture['away'])}: **{away_staked:,}** coins · {away_bettors} bettor(s)",
                    f"-# Total pool: **{total_pool:,}** coins",
                ])
            )
        children.append(ui.TextDisplay("\n\n".join(blocks)))

    if total_pages > 1:
        prev_btn = ui.Button(label='◀', style=discord.ButtonStyle.secondary, disabled=safe_page <= 0)
        next_btn = ui.Button(
            label='▶', style=discord.ButtonStyle.secondary, disabled=safe_page >= total_pages - 1,
        )

        async def prev_cb(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(view=_build_board_page(fixtures, safe_page - 1))

        async def next_cb(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(view=_build_board_page(fixtures, safe_page + 1))

        prev_btn.callback = prev_cb
        next_btn.callback = next_cb
        children.extend([
            ui.Separator(),
            ui.ActionRow(prev_btn, next_btn),
            ui.TextDisplay(f"-# Page {safe_page + 1}/{total_pages}"),
        ])

    view.add_item(ui.Container(*children, accent_colour=discord.Color.gold()))
    return view


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

    async def cog_load(self) -> None:
        """Overlay any stored knockout team overrides onto the fixtures.

        Knockout fixtures ship with bracket placeholders; resolved pairings
        are persisted in `wc_fixture_overrides` and re-applied here on every
        startup so betting/settlement survive restarts. Failures are logged
        but non-fatal — the bot still runs with unresolved knockouts.
        """
        try:
            overrides = await self.bot.db.get_wc_fixture_overrides()
        except Exception:
            logger.exception("wcbet: failed to load knockout fixture overrides")
            return
        applied = apply_fixture_overrides(overrides)
        if applied:
            logger.info("wcbet: applied %s knockout fixture override(s)", applied)

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
        labels = await resolve_member_labels(
            self.bot, ctx.guild, [r["user_id"] for r in rows],
        )
        lines = [
            f"{i}. {labels[r['user_id']]} — **{r['balance']:,}** coins"
            for i, r in enumerate(rows, 1)
        ]
        await ctx.send(embed=blue_embed("🏆 **WC Betting Leaderboard**\n" + "\n".join(lines)))

    @commands.command(name="wcbetme")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def wcbetme(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        """Show your (or another member's) World Cup betting profile."""
        target = member or ctx.author
        profile = await self.bot.db.get_wc_user_profile(target.id, ctx.guild.id)
        if profile["total_bets"] == 0 and profile["balance"] == 0:
            await ctx.send(embed=blue_embed(f"{target.display_name} hasn't placed any bets yet."))
            return
        await ctx.send(embed=_build_profile_embed(target, profile))

    @commands.command(name="wcbethistory")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def wcbethistory(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        """Show your (or another member's) recent World Cup betting balance history."""
        target = member or ctx.author
        history = await self.bot.db.get_wc_balance_history(target.id)
        await ctx.send(view=_build_history_page(target, history, 0))

    @commands.command(name="wcbetboard")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.guild_only()
    async def wcbetboard(self, ctx: commands.Context) -> None:
        """Show aggregate pending singles for the current bettable matches."""
        fixtures = betting.bettable_fixtures(datetime.now(UTC))
        if not fixtures:
            await ctx.send(view=_build_board_page([], 0))
            return

        multiplier = await self.bot.db.get_wc_odds_multiplier()
        odds_map = await espn.fetch_match_odds(fixtures, multiplier)
        board_map = await self.bot.db.get_wc_pending_market_board(
            [fixture['match_id'] for fixture in fixtures],
        )
        rows = [
            {
                'fixture': fixture,
                'odds': odds_map.get(fixture['match_id']),
                'board': board_map.get(fixture['match_id'], {}),
            }
            for fixture in fixtures
        ]
        for row in rows:
            if row['odds'] is None:
                row['odds'] = _fallback_board_odds(multiplier)
        await ctx.send(view=_build_board_page(rows, 0))

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
        fixture = FIXTURE_BY_ID.get(match_id)
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
        player_msg = format_player_results(summary.get("bets", []), label=label)
        if player_msg:
            await self._announce(player_msg, channel_id=WCBET_NOTIFICATION_CHANNEL_ID)
        parlay_msg = format_parlay_results(summary.get("parlays", []))
        if parlay_msg:
            await self._announce(parlay_msg, channel_id=WCBET_NOTIFICATION_CHANNEL_ID)

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
