"""Views for the World Cup betting cog.

Follows the `$wt` pattern (`cogs/interactions_cog/main.py`): a prefix
command sends a small public button prompt (`OpenBetPanelView`); clicking
it opens a personal **ephemeral** Components V2 panel (`BetPanelView`)
that rebuilds itself in place on every step: match → outcome → stake →
confirm. Stake amounts are picked from a select whose options carry the
exact payout at the selected outcome's odds; `StakeModal` survives only
as the "Custom amount…" escape hatch and never commits a bet itself.

Every callback re-validates against `betting.bettable_fixtures` so a
match that kicked off mid-flow disappears and the selection resets. The
Place button commits at re-resolved odds and refuses if the price moved
from what it displayed.
"""
import contextlib
import logging
from datetime import UTC, datetime
from decimal import Decimal

import discord
from discord import (
    ButtonStyle,
    Color,
    Interaction,
    SelectOption,
    TextStyle,
    ui,
)
from discord.ext import commands

from cogs.wcpredict_cog.fixtures import FIXTURE_BY_ID, Fixture
from cogs.wcpredict_cog.fixtures_view import TEAM_FLAGS
from db.bets import InsufficientBalanceError, MatchAlreadySettledError

from . import betting, espn
from .config import (
    WCBET_DAILY_ALLOWANCE,
    WCBET_LOG_CHANNEL_ID,
    WCBET_ODDS,
    WCBET_STARTING_BALANCE,
)
from .results import MatchOdds

logger = logging.getLogger(__name__)

# outcome -> (emoji, button label)
OUTCOME_BUTTONS: dict[str, tuple[str, str]] = {
    "home": ("🏠", "Home"),
    "draw": ("🤝", "Draw"),
    "away": ("✈️", "Away"),
}

STATUS_EMOJI: dict[str, str] = {
    "pending": "⏳",
    "won": "✅",
    "lost": "❌",
    "void": "↩️",
}


def _flat_odds() -> MatchOdds:
    """Fallback odds when DraftKings has no line for a match."""
    return MatchOdds(home=WCBET_ODDS, draw=WCBET_ODDS, away=WCBET_ODDS)


def _now_utc() -> datetime:
    """Current UTC time — module-level seam so tests can freeze the clock."""
    return datetime.now(UTC)


def _team_label(name: str) -> str:
    """Return 'FLAG Name' for known teams, or just 'Name' otherwise."""
    flag = TEAM_FLAGS.get(name, "")
    return f"{flag} {name}".strip()


def _outcome_label(outcome: str, fixture: Fixture) -> str:
    """Human-readable label for a bet outcome on a fixture."""
    if outcome == "home":
        return _team_label(fixture["home"])
    if outcome == "away":
        return _team_label(fixture["away"])
    return "Draw"


# ── Log channel helpers (shape: cogs/wcpredict_cog/views.py) ─────────────────

async def _get_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel = guild.get_channel(WCBET_LOG_CHANNEL_ID)
    if channel is None:
        logger.warning(
            "Bet log channel %s not found in guild %s", WCBET_LOG_CHANNEL_ID, guild.id,
        )
    return channel


async def _log_bet(
    interaction: Interaction,
    fixture: Fixture,
    outcome: str,
    stake: int,
    odds: Decimal,
) -> None:
    """Log a placed bet to the World Cup log channel."""
    if interaction.guild is None:
        return
    channel = await _get_log_channel(interaction.guild)
    if channel is None:
        return

    embed = discord.Embed(color=discord.Color.blurple())
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.description = (
        f"**{interaction.user}** bet **{stake:,}** coins @ **{odds}** on "
        f"**{_outcome_label(outcome, fixture)}** in "
        f"{_team_label(fixture['home'])} vs {_team_label(fixture['away'])} "
        f"(match {fixture['match_id']})."
    )
    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException) as exc:
        logger.error(
            "Failed to send bet log to channel %s: %s", WCBET_LOG_CHANNEL_ID, exc,
        )


# ── Public prompt ─────────────────────────────────────────────────────────────

class OpenBetPanelView(ui.View):
    """Public prompt — anyone clicks the button to get their own panel.

    Classic `ui.View` (no V2 items); the rich panel itself is the
    ephemeral `BetPanelView` LayoutView sent per clicker.
    """

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.prompt_message: discord.Message | None = None

    @ui.button(label="Make prediction", emoji="🎰", style=ButtonStyle.primary)
    async def open_panel(self, interaction: Interaction, button: ui.Button) -> None:
        await self._open_for(interaction)

    async def _open_for(self, interaction: Interaction) -> None:
        """Open the personal panel for the clicker (extracted for testing)."""
        user_id = interaction.user.id
        if await self.bot.db.is_wc_bet_banned(user_id):
            await interaction.response.send_message(
                content=(
                    "🚫 You're banned from World Cup betting. Contact a moderator "
                    "if you think this is a mistake."
                ),
                ephemeral=True,
            )
            return
        wallet = await self.bot.db.get_wc_wallet(user_id)
        if wallet is None:
            optin = OptInView(self.bot, user_id=user_id, guild_id=interaction.guild_id)
            await interaction.response.send_message(view=optin, ephemeral=True)
            return

        balance: int = wallet["balance"]
        notice: str | None = None
        new_balance = await self.bot.db.claim_wc_daily_allowance(
            user_id, WCBET_DAILY_ALLOWANCE, _now_utc().date(),
        )
        if new_balance is not None:
            balance = new_balance
            notice = f"+{WCBET_DAILY_ALLOWANCE} daily allowance claimed!"

        panel = BetPanelView(
            self.bot, user_id=user_id, guild_id=interaction.guild_id,
            balance=balance, notice=notice,
        )
        await panel.refresh()
        await interaction.response.send_message(view=panel, ephemeral=True)

    async def on_timeout(self) -> None:
        self.open_panel.disabled = True
        if self.prompt_message:
            with contextlib.suppress(discord.NotFound, discord.HTTPException):
                await self.prompt_message.edit(
                    content="Betting prompt expired — run the command again.",
                    view=None,
                )


# ── Opt-in panel ──────────────────────────────────────────────────────────────

class OptInView(ui.LayoutView):
    """Ephemeral opt-in explainer shown to users without a wallet."""

    def __init__(self, bot: commands.Bot, *, user_id: int, guild_id: int) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id

        opt_in = ui.Button(
            label=f"Opt in — get {WCBET_STARTING_BALANCE:,} coins",
            emoji="🪙",
            style=ButtonStyle.success,
        )
        opt_in.callback = self._opt_in
        self.add_item(ui.Container(
            ui.TextDisplay(
                "## 🎰 World Cup betting\n"
                "Bet virtual coins on today's group-stage matches — pick a "
                "match, an outcome (home / draw / away), and a stake. "
                "Payouts follow real bookmaker odds (DraftKings via ESPN), "
                "so underdogs pay big; you can replace a bet any time "
                "before kickoff.\n"
                f"-# Opting in grants a one-time **{WCBET_STARTING_BALANCE:,}** "
                f"coins, plus **+{WCBET_DAILY_ALLOWANCE}** on your first visit "
                "each day."
            ),
            ui.Separator(),
            ui.ActionRow(opt_in),
            accent_colour=Color.blurple(),
        ))

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def _opt_in(self, interaction: Interaction) -> None:
        created = await self.bot.db.create_wc_wallet(
            self.user_id, self.guild_id, WCBET_STARTING_BALANCE,
        )
        wallet = await self.bot.db.get_wc_wallet(self.user_id)
        balance: int = wallet["balance"] if wallet else WCBET_STARTING_BALANCE
        notice = (
            f"Welcome! You start with **{WCBET_STARTING_BALANCE:,}** coins."
            if created else None
        )
        panel = BetPanelView(
            self.bot, user_id=self.user_id, guild_id=self.guild_id,
            balance=balance, notice=notice,
        )
        await panel.refresh()
        await interaction.response.edit_message(view=panel)

    async def on_timeout(self) -> None:
        logger.debug("OptInView timed out for user %s", self.user_id)


# ── Betting panel ─────────────────────────────────────────────────────────────

class BetPanelView(ui.LayoutView):
    """Personal ephemeral stepper: match → outcome → stake.

    Holds the selection state and is rebuilt in place on every step via
    `interaction.response.edit_message(view=self)`.
    """

    def __init__(
        self,
        bot: commands.Bot,
        *,
        user_id: int,
        guild_id: int,
        balance: int,
        notice: str | None = None,
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id
        self.balance = balance
        self.notice = notice
        self.selected_match_id: int | None = None
        self.selected_outcome: str | None = None
        self.selected_stake: int | None = None
        self.show_history = False
        # Set when a live-odds re-fetch fails at placement; surfaces the
        # explicit "place at fallback odds" escape hatch.
        self._odds_blip = False

        self._fixtures: list[Fixture] = []
        self._pending: dict[int, object] = {}
        self._history: list = []
        self._odds: dict[int, MatchOdds] = {}
        # Odds the Place button displayed when armed — drift guard.
        self._armed_odds: Decimal | None = None
        # Rebuilt-item references (also used by tests to assert state).
        self._match_select: ui.Select | None = None
        self._outcome_buttons: dict[str, ui.Button] = {}
        self._stake_select: ui.Select | None = None
        self._place_button: ui.Button | None = None
        self._fallback_button: ui.Button | None = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user_id

    # ---------- state ----------

    def _selected_fixture(self, now_utc: datetime) -> Fixture | None:
        """The selected fixture if it is still bettable, else None."""
        if self.selected_match_id is None:
            return None
        for fixture in betting.bettable_fixtures(now_utc):
            if fixture["match_id"] == self.selected_match_id:
                return fixture
        return None

    def _odds_for(self, match_id: int) -> MatchOdds:
        """Decimal odds for a match, falling back to the flat default."""
        return self._odds.get(match_id, _flat_odds())

    async def refresh(self) -> None:
        """Recompute fixtures, odds, and the user's bets, then rebuild."""
        now = _now_utc()
        # The fallback button is tied to one specific blip; any path that
        # re-fetches odds (selection change, retry) clears it.
        self._odds_blip = False
        self._fixtures = betting.bettable_fixtures(now)
        valid_ids = {f["match_id"] for f in self._fixtures}
        if self.selected_match_id is not None and self.selected_match_id not in valid_ids:
            self.selected_match_id = None
            self.selected_outcome = None
            self.selected_stake = None
            self.notice = "That match has kicked off — pick another."
        if self.selected_stake is not None and self.selected_stake > self.balance:
            self.selected_stake = None

        self._odds = await espn.fetch_match_odds(self._fixtures)

        self._pending = {}
        for fixture in self._fixtures:
            bet = await self.bot.db.get_wc_user_bet(self.user_id, fixture["match_id"])
            if bet is not None:
                self._pending[fixture["match_id"]] = bet

        if self.show_history:
            self._history = await self.bot.db.get_wc_user_bets(self.user_id)

        self._rebuild()

    # ---------- rendering ----------

    def _header(self) -> str:
        header = f"## 🎰 World Cup betting\n💰 Balance: **{self.balance:,}** coins"
        if self.notice:
            header += f"\n-# {self.notice}"
        return header

    def _step_hint(self, selected: Fixture | None) -> str:
        """One-line 'do this next' nudge keyed to the current selection."""
        if selected is None:
            return "-# Step 1 of 3 — pick a match below."
        if self.selected_outcome is None:
            return "-# Step 2 of 3 — who wins? (home / draw / away)"
        if self.selected_stake is None:
            return "-# Step 3 of 3 — choose your stake."
        return "-# Ready — review your slip and press **Place bet**."

    def _match_list_lines(self) -> list[str]:
        """Compact 'today's matches' list shown before a match is chosen.

        Once a match is selected the focused slip replaces this, so the
        same matches are never listed twice.
        """
        lines: list[str] = []
        for fixture in self._fixtures:
            ts = int(betting.kickoff_utc(fixture).timestamp())
            odds = self._odds_for(fixture["match_id"])
            lines.append(
                f"**{_team_label(fixture['home'])}** vs "
                f"**{_team_label(fixture['away'])}** — kickoff <t:{ts}:t>\n"
                f"-# odds {odds['home']} / {odds['draw']} / {odds['away']}"
            )
            bet = self._pending.get(fixture["match_id"])
            if bet is not None:
                lines.append(
                    f"-# 🎟️ you have {bet['stake']:,} @ {bet['odds']} on "
                    f"{_outcome_label(bet['outcome'], fixture)}"
                )
        return lines

    def _slip_lines(self, selected: Fixture, selected_odds: MatchOdds) -> list[str]:
        """Focused card for the selected match: kickoff, your current bet,
        and a running bet-slip summary that fills in as steps complete.
        """
        ts = int(betting.kickoff_utc(selected).timestamp())
        lines = [
            f"### {_team_label(selected['home'])} vs {_team_label(selected['away'])}",
            f"-# Group {selected['group']} · kickoff <t:{ts}:R> "
            f"· odds {selected_odds['home']} / {selected_odds['draw']} "
            f"/ {selected_odds['away']}",
        ]
        existing = self._pending.get(selected["match_id"])
        if existing is not None:
            lines.append(
                f"-# 🎟️ current bet: {existing['stake']:,} @ {existing['odds']} on "
                f"**{_outcome_label(existing['outcome'], selected)}** "
                "— placing again replaces it."
            )

        # Running bet slip — only the parts chosen so far.
        if self.selected_outcome is not None:
            pick = _outcome_label(self.selected_outcome, selected)
            price = selected_odds[self.selected_outcome]
            if self.selected_stake is not None:
                win = betting.payout(self.selected_stake, price)
                slip = (
                    f"🧾 **Bet slip:** {self.selected_stake:,} on **{pick}** "
                    f"@ **{price}** → win **{win:,}**"
                )
            else:
                slip = f"🧾 **Bet slip:** **{pick}** @ **{price}** — add a stake."
            lines.append(slip)
        return lines

    def _rebuild(self) -> None:
        """Clear and re-add all items from current state."""
        self.clear_items()
        self._match_select = None
        self._outcome_buttons = {}
        self._stake_select = None
        self._place_button = None
        self._fallback_button = None
        self._armed_odds = None

        if self.show_history:
            self._rebuild_history()
            return

        children: list[ui.Item] = [ui.TextDisplay(self._header()), ui.Separator()]

        if not self._fixtures:
            children.append(ui.TextDisplay(
                "No more bettable matches today — come back tomorrow!",
            ))
        else:
            selected = next(
                (f for f in self._fixtures if f["match_id"] == self.selected_match_id),
                None,
            )
            selected_odds = (
                self._odds_for(selected["match_id"]) if selected is not None else None
            )

            # Step nudge so it is always obvious what to do next.
            children.append(ui.TextDisplay(self._step_hint(selected)))

            # Before a match is chosen: a compact list of today's matches.
            # After: a focused slip for that one match (no duplicate listing).
            if selected is None:
                children.append(ui.TextDisplay("\n".join(self._match_list_lines())))
            else:
                children.append(ui.TextDisplay("\n".join(
                    self._slip_lines(selected, selected_odds),
                )))
            children.append(ui.Separator())

            select = ui.Select(
                placeholder="Choose a match…",
                options=[
                    SelectOption(
                        label=f"{fixture['home']} vs {fixture['away']}",
                        value=str(fixture["match_id"]),
                        description=f"Group {fixture['group']} — kickoff {fixture['time_et']} ET",
                        default=fixture["match_id"] == self.selected_match_id,
                    )
                    for fixture in self._fixtures
                ],
            )
            select.callback = self._make_select_callback(select)
            self._match_select = select
            children.append(ui.ActionRow(select))

            outcome_buttons: list[ui.Button] = []
            for outcome, (emoji, label) in OUTCOME_BUTTONS.items():
                if selected is not None and outcome != "draw":
                    team = selected["home"] if outcome == "home" else selected["away"]
                    label = team
                    emoji = TEAM_FLAGS.get(team, emoji)
                if selected_odds is not None:
                    label = f"{label} · {selected_odds[outcome]}"
                button = ui.Button(
                    label=label,
                    emoji=emoji,
                    style=(
                        ButtonStyle.success
                        if outcome == self.selected_outcome
                        else ButtonStyle.secondary
                    ),
                    disabled=self.selected_match_id is None,
                )
                button.callback = self._make_outcome_callback(outcome)
                self._outcome_buttons[outcome] = button
                outcome_buttons.append(button)
            children.append(ui.ActionRow(*outcome_buttons))

            # Stake select: payouts live in the option labels, priced at
            # the selected outcome's odds.
            pick_odds = (
                selected_odds[self.selected_outcome]
                if selected_odds is not None and self.selected_outcome is not None
                else None
            )
            if pick_odds is not None:
                amounts = betting.stake_presets(self.balance)
                if self.selected_stake is not None and self.selected_stake not in amounts:
                    amounts.insert(0, self.selected_stake)
                stake_options = [
                    SelectOption(
                        label=(
                            f"All in ({amount:,}) → pays "
                            f"{betting.payout(amount, pick_odds):,}"
                            if amount == self.balance
                            else f"{amount:,} → pays {betting.payout(amount, pick_odds):,}"
                        ),
                        value=str(amount),
                        default=amount == self.selected_stake,
                    )
                    for amount in amounts
                ]
                stake_options.append(
                    SelectOption(label="Custom amount…", value="custom", emoji="✏️")
                )
            else:
                stake_options = [SelectOption(label="—", value="none")]
            stake_select = ui.Select(
                placeholder=(
                    "Choose your stake…" if pick_odds is not None
                    else "Pick an outcome first"
                ),
                options=stake_options,
                disabled=pick_odds is None,
            )
            stake_select.callback = self._make_stake_callback(stake_select)
            self._stake_select = stake_select
            children.append(ui.ActionRow(stake_select))

            armed = pick_odds is not None and self.selected_stake is not None
            if armed:
                self._armed_odds = pick_odds
                win = betting.payout(self.selected_stake, pick_odds)
                place_label = f"Place {self.selected_stake:,} → win {win:,}"
            elif pick_odds is not None:
                place_label = "Place bet — pick a stake"
            elif self.selected_match_id is not None:
                place_label = "Place bet — pick an outcome"
            else:
                place_label = "Place bet — pick a match"
            place = ui.Button(
                label=place_label,
                emoji="💸",
                style=ButtonStyle.primary,
                disabled=not armed,
            )
            place.callback = self._on_place_bet
            self._place_button = place

            my_bets = ui.Button(label="My bets", emoji="📜", style=ButtonStyle.secondary)
            my_bets.callback = self._on_my_bets
            close = ui.Button(label="Close", emoji="✖️", style=ButtonStyle.secondary)
            close.callback = self._on_close
            children.append(ui.Separator())

            # After a live-odds re-fetch failure, offer an explicit opt-in to
            # bet at the flat fallback price instead of being blocked.
            if self._odds_blip and armed:
                fallback = ui.Button(
                    label=f"Place @ {WCBET_ODDS}",
                    emoji="⚠️",
                    style=ButtonStyle.danger,
                )
                fallback.callback = self._on_place_fallback
                self._fallback_button = fallback
                children.append(ui.ActionRow(place, fallback, my_bets, close))
            else:
                children.append(ui.ActionRow(place, my_bets, close))

        self.add_item(ui.Container(*children, accent_colour=Color.blurple()))

    def _rebuild_history(self) -> None:
        """Render the user's bet history with a Back button."""
        if self._history:
            lines = []
            for bet in self._history:
                fixture = FIXTURE_BY_ID.get(bet["match_id"])
                match_label = (
                    f"{_team_label(fixture['home'])} vs {_team_label(fixture['away'])}"
                    if fixture else f"match {bet['match_id']}"
                )
                outcome_label = (
                    _outcome_label(bet["outcome"], fixture) if fixture else bet["outcome"]
                )
                status = bet["status"]
                line = (
                    f"{STATUS_EMOJI.get(status, '•')} **{bet['stake']:,}** "
                    f"@ {bet['odds']} on **{outcome_label}** — {match_label}"
                )
                if status == "won" and bet["payout"] is not None:
                    line += f" (paid **{bet['payout']:,}**)"
                lines.append(line)
            body = "\n".join(lines)
        else:
            body = "No bets yet — place your first one!"

        back = ui.Button(label="Back", emoji="↩️", style=ButtonStyle.secondary)
        back.callback = self._on_back
        close = ui.Button(label="Close", emoji="✖️", style=ButtonStyle.secondary)
        close.callback = self._on_close
        self.add_item(ui.Container(
            ui.TextDisplay(f"## 📜 My bets\n💰 Balance: **{self.balance:,}** coins"),
            ui.Separator(),
            ui.TextDisplay(body),
            ui.Separator(),
            ui.ActionRow(back, close),
            accent_colour=Color.blurple(),
        ))

    # ---------- callbacks ----------

    def _make_select_callback(self, select: ui.Select):
        async def callback(interaction: Interaction) -> None:
            match_id: int | None = None
            if select.values:
                try:
                    match_id = int(select.values[0])
                except ValueError:
                    match_id = None
            if match_id != self.selected_match_id:
                self.selected_match_id = match_id
                self.selected_outcome = None
            self.notice = None
            await self.refresh()
            await interaction.response.edit_message(view=self)

        return callback

    def _make_outcome_callback(self, outcome: str):
        async def callback(interaction: Interaction) -> None:
            if self.selected_match_id is not None:
                self.selected_outcome = outcome
                self.notice = None
            await self.refresh()
            await interaction.response.edit_message(view=self)

        return callback

    def _make_stake_callback(self, select: ui.Select):
        async def callback(interaction: Interaction) -> None:
            value = select.values[0] if select.values else None
            if value == "custom":
                await interaction.response.send_modal(StakeModal(self))
                return
            try:
                stake = int(value)
            except (TypeError, ValueError):
                stake = None
            if stake is not None and not 1 <= stake <= self.balance:
                stake = None
            self.selected_stake = stake
            self.notice = None
            await self.refresh()
            await interaction.response.edit_message(view=self)

        return callback

    async def _on_place_bet(self, interaction: Interaction) -> None:
        """Commit the armed bet at freshly resolved odds (drift-guarded)."""
        fixture = self._selected_fixture(_now_utc())
        outcome = self.selected_outcome
        stake = self.selected_stake
        armed = self._armed_odds
        if fixture is None or outcome is None or stake is None or armed is None:
            self._odds_blip = False
            await self.refresh()
            await interaction.response.edit_message(view=self)
            return

        match_id = fixture["match_id"]
        current_map = await espn.fetch_match_odds([fixture])
        fresh = current_map.get(match_id)
        if fresh is None and armed != WCBET_ODDS:
            # We armed at a real DraftKings price but the re-fetch returned
            # nothing for this match. That is almost always a transient ESPN
            # blip, not the line being pulled — silently dropping to the flat
            # 1.5 fallback would quietly reprice an underdog bet downward.
            # Skip refresh() (it would re-fetch the now-empty odds and clobber
            # the armed price); just surface the notice so a retry stays at
            # the armed price, and expose the explicit fallback button.
            self._odds_blip = True
            self.notice = (
                "Couldn't refresh the live odds just now — press **Place bet** "
                f"to retry at your armed price (**{armed}**), or use "
                f"**Place @ {WCBET_ODDS}** to bet at the fallback price."
            )
            self._rebuild()
            await interaction.response.edit_message(view=self)
            return
        current = (fresh or _flat_odds())[outcome]
        if current != armed:
            self._odds_blip = False
            self.notice = (
                f"Odds moved **{armed} → {current}** — confirm again at the "
                "new price."
            )
            await self.refresh()
            await interaction.response.edit_message(view=self)
            return

        await self._commit_bet(interaction, fixture, outcome, stake, current)

    async def _on_place_fallback(self, interaction: Interaction) -> None:
        """Commit at the flat fallback odds — a conscious downgrade the user
        opts into when live odds are unreachable."""
        fixture = self._selected_fixture(_now_utc())
        outcome = self.selected_outcome
        stake = self.selected_stake
        if fixture is None or outcome is None or stake is None:
            self._odds_blip = False
            await self.refresh()
            await interaction.response.edit_message(view=self)
            return
        await self._commit_bet(interaction, fixture, outcome, stake, WCBET_ODDS)

    async def _commit_bet(
        self,
        interaction: Interaction,
        fixture: Fixture,
        outcome: str,
        stake: int,
        odds: Decimal,
    ) -> None:
        """Place the bet at `odds` and reset the stepper on success."""
        match_id = fixture["match_id"]
        try:
            new_balance = await self.bot.db.place_wc_bet(
                self.user_id, self.guild_id, match_id, outcome, stake, odds,
            )
        except InsufficientBalanceError:
            self.notice = "Not enough coins for that stake."
        except MatchAlreadySettledError:
            self.notice = "That match was already settled — your bet was not placed."
        else:
            self.balance = new_balance
            win = betting.payout(stake, odds)
            self.notice = (
                f"Bet placed: **{stake:,}** on **{_outcome_label(outcome, fixture)}** "
                f"@ **{odds}** — pays **{win:,}** if it lands. "
                f"New balance: **{new_balance:,}**."
            )
            self.selected_match_id = None
            self.selected_outcome = None
            self.selected_stake = None
            logger.info(
                "User %s bet %s @ %s on %s in match %s",
                self.user_id, stake, odds, outcome, match_id,
            )
            await _log_bet(interaction, fixture, outcome, stake, odds)
        self._odds_blip = False
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def _on_my_bets(self, interaction: Interaction) -> None:
        self.show_history = True
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def _on_back(self, interaction: Interaction) -> None:
        self.show_history = False
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def _on_close(self, interaction: Interaction) -> None:
        """Dismiss the personal panel, collapsing it to a short notice."""
        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay(
                "🎰 Betting panel closed — run `$wcbet` again to reopen."
            ),
            accent_colour=Color.blurple(),
        ))
        self.stop()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self) -> None:
        logger.debug("BetPanelView timed out for user %s", self.user_id)


# ── Stake modal ───────────────────────────────────────────────────────────────

class StakeModal(ui.Modal, title="Custom stake"):
    """Single-field modal for custom stake amounts.

    Never commits a bet — it sets the panel's `selected_stake` and
    re-renders, so custom amounts get the same preview-then-confirm
    treatment as the preset picks.
    """

    def __init__(self, panel: BetPanelView) -> None:
        super().__init__()
        self.panel = panel
        self.stake_input = ui.TextInput(
            style=TextStyle.short,
            placeholder="e.g. 500 — or 'all'",
            max_length=20,
        )
        self.add_item(ui.Label(text="Coins to bet", component=self.stake_input))

    async def on_submit(self, interaction: Interaction) -> None:
        panel = self.panel
        stake = betting.parse_stake(self.stake_input.value, panel.balance)
        if stake is None:
            panel.notice = (
                "Couldn't read that stake — enter a whole number between 1 "
                "and your balance, or 'all'."
            )
        else:
            panel.selected_stake = stake
            panel.notice = None
        await panel.refresh()
        await interaction.response.edit_message(view=panel)
