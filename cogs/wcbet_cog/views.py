"""Views for the World Cup betting cog.

Follows the `$wt` pattern (`cogs/interactions_cog/main.py`): a prefix
command sends a small public button prompt (`OpenBetPanelView`); clicking
it opens a personal **ephemeral** Components V2 panel (`BetPanelView`)
that rebuilds itself in place on every step. The stake is collected with
a single-field modal (`StakeModal`).

Every callback re-validates against `betting.bettable_fixtures` so a
match that kicked off mid-flow disappears and the selection resets.
"""
import contextlib
import logging
from datetime import UTC, datetime

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

from . import betting
from .config import (
    WCBET_DAILY_ALLOWANCE,
    WCBET_LOG_CHANNEL_ID,
    WCBET_ODDS,
    WCBET_STARTING_BALANCE,
)

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
        f"**{interaction.user}** bet **{stake:,}** coins on "
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
        user_id = interaction.user.id
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
                f"Correct bets pay **{WCBET_ODDS}x**; you can replace a bet "
                "any time before kickoff.\n"
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
        self.show_history = False

        self._fixtures: list[Fixture] = []
        self._pending: dict[int, object] = {}
        self._history: list = []
        # Rebuilt-item references (also used by tests to assert state).
        self._match_select: ui.Select | None = None
        self._outcome_buttons: dict[str, ui.Button] = {}
        self._place_button: ui.Button | None = None

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

    async def refresh(self) -> None:
        """Recompute bettable fixtures + the user's bets, then rebuild."""
        now = _now_utc()
        self._fixtures = betting.bettable_fixtures(now)
        valid_ids = {f["match_id"] for f in self._fixtures}
        if self.selected_match_id is not None and self.selected_match_id not in valid_ids:
            self.selected_match_id = None
            self.selected_outcome = None
            self.notice = "That match has kicked off — pick another."

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

    def _rebuild(self) -> None:
        """Clear and re-add all items from current state."""
        self.clear_items()
        self._match_select = None
        self._outcome_buttons = {}
        self._place_button = None

        if self.show_history:
            self._rebuild_history()
            return

        children: list[ui.Item] = [ui.TextDisplay(self._header()), ui.Separator()]

        if not self._fixtures:
            children.append(ui.TextDisplay(
                "No more bettable matches today — come back tomorrow!",
            ))
        else:
            lines: list[str] = []
            for fixture in self._fixtures:
                ts = int(betting.kickoff_utc(fixture).timestamp())
                marker = "▶️ " if fixture["match_id"] == self.selected_match_id else ""
                lines.append(
                    f"{marker}**{_team_label(fixture['home'])}** vs "
                    f"**{_team_label(fixture['away'])}** — kickoff <t:{ts}:t>"
                )
                bet = self._pending.get(fixture["match_id"])
                if bet is not None:
                    lines.append(
                        f"-# you have {bet['stake']:,} on "
                        f"{_outcome_label(bet['outcome'], fixture)}"
                    )
            children.append(ui.TextDisplay("\n".join(lines)))
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

            selected = next(
                (f for f in self._fixtures if f["match_id"] == self.selected_match_id),
                None,
            )
            outcome_buttons: list[ui.Button] = []
            for outcome, (emoji, label) in OUTCOME_BUTTONS.items():
                if selected is not None and outcome != "draw":
                    team = selected["home"] if outcome == "home" else selected["away"]
                    label = team
                    emoji = TEAM_FLAGS.get(team, emoji)
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

            place = ui.Button(
                label="Place bet…",
                emoji="💸",
                style=ButtonStyle.primary,
                disabled=self.selected_match_id is None or self.selected_outcome is None,
            )
            place.callback = self._on_place_bet
            self._place_button = place

            my_bets = ui.Button(label="My bets", emoji="📜", style=ButtonStyle.secondary)
            my_bets.callback = self._on_my_bets
            children.append(ui.ActionRow(place, my_bets))

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
                    f"{STATUS_EMOJI.get(status, '•')} **{bet['stake']:,}** on "
                    f"**{outcome_label}** — {match_label}"
                )
                if status == "won" and bet["payout"] is not None:
                    line += f" (paid **{bet['payout']:,}**)"
                lines.append(line)
            body = "\n".join(lines)
        else:
            body = "No bets yet — place your first one!"

        back = ui.Button(label="Back", emoji="↩️", style=ButtonStyle.secondary)
        back.callback = self._on_back
        self.add_item(ui.Container(
            ui.TextDisplay(f"## 📜 My bets\n💰 Balance: **{self.balance:,}** coins"),
            ui.Separator(),
            ui.TextDisplay(body),
            ui.Separator(),
            ui.ActionRow(back),
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

    async def _on_place_bet(self, interaction: Interaction) -> None:
        fixture = self._selected_fixture(_now_utc())
        if fixture is None or self.selected_outcome is None:
            await self.refresh()
            await interaction.response.edit_message(view=self)
            return
        await interaction.response.send_modal(StakeModal(self))

    async def _on_my_bets(self, interaction: Interaction) -> None:
        self.show_history = True
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def _on_back(self, interaction: Interaction) -> None:
        self.show_history = False
        await self.refresh()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self) -> None:
        logger.debug("BetPanelView timed out for user %s", self.user_id)


# ── Stake modal ───────────────────────────────────────────────────────────────

class StakeModal(ui.Modal, title="Stake"):
    """Single-field modal collecting the stake for the selected bet."""

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
            await panel.refresh()
            await interaction.response.edit_message(view=panel)
            return

        fixture = panel._selected_fixture(_now_utc())
        outcome = panel.selected_outcome
        if fixture is None or outcome is None:
            panel.selected_match_id = None
            panel.selected_outcome = None
            panel.notice = "That match has kicked off — your bet was not placed."
            await panel.refresh()
            await interaction.response.edit_message(view=panel)
            return

        try:
            new_balance = await panel.bot.db.place_wc_bet(
                panel.user_id, panel.guild_id, fixture["match_id"],
                outcome, stake, WCBET_ODDS,
            )
        except InsufficientBalanceError:
            panel.notice = "Not enough coins for that stake."
        except MatchAlreadySettledError:
            panel.notice = "That match was already settled — your bet was not placed."
        else:
            panel.balance = new_balance
            panel.selected_match_id = None
            panel.selected_outcome = None
            panel.notice = (
                f"Bet placed: **{stake:,}** on **{_outcome_label(outcome, fixture)}** — "
                f"potential payout **{betting.payout(stake):,}**. "
                f"New balance: **{new_balance:,}**."
            )
            logger.info(
                "wcbet: user %s bet %s on %s (match %s)",
                panel.user_id, stake, outcome, fixture["match_id"],
            )
            await _log_bet(interaction, fixture, outcome, stake)

        await panel.refresh()
        await interaction.response.edit_message(view=panel)
