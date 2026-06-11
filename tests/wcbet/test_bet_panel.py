"""Tests for the betting panel views — stake arming, kickoff races,
odds pricing, the drift guard, and stepper state. Pure-logic coverage
lives in test_betting.py; odds parsing in test_results.py."""
from datetime import UTC, datetime
from decimal import Decimal

from discord import ButtonStyle

from cogs.wcbet_cog import views
from cogs.wcbet_cog.config import WCBET_ODDS
from cogs.wcbet_cog.results import MatchOdds

from .conftest import GUILD_ID, USER_ID

MATCH_1_ODDS = MatchOdds(
    home=Decimal("1.43"), draw=Decimal("4.40"), away=Decimal("8.50"),
)


async def _open_panel(fake_bot) -> views.BetPanelView:
    panel = views.BetPanelView(
        fake_bot, user_id=USER_ID, guild_id=GUILD_ID, balance=10_000,
    )
    await panel.refresh()
    return panel


async def _armed_panel(fake_bot, outcome: str = "away", stake: int = 500):
    """Panel with match 1 + outcome + stake selected (Place button armed)."""
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = outcome
    panel.selected_stake = stake
    await panel.refresh()
    return panel


def _modal_with_stake(panel: views.BetPanelView, raw: str) -> views.StakeModal:
    modal = views.StakeModal(panel)
    modal.stake_input._value = raw  # what discord fills in from the submit payload
    return modal


# ── custom stake modal (arms, never commits) ─────────────────────────────────

async def test_invalid_stake_rejected_without_db_call(fake_bot, interaction, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "home"
    await panel.refresh()

    modal = _modal_with_stake(panel, "not-a-number")
    await modal.on_submit(interaction)

    assert fake_bot.db.place_calls == []
    assert panel.selected_stake is None
    assert panel.notice is not None
    assert interaction.response.edited  # panel re-rendered with the notice


async def test_custom_stake_arms_but_does_not_commit(fake_bot, interaction, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "away"
    await panel.refresh()

    modal = _modal_with_stake(panel, "500")
    await modal.on_submit(interaction)

    assert fake_bot.db.place_calls == []  # nothing committed
    assert panel.selected_stake == 500
    assert panel._place_button is not None and not panel._place_button.disabled
    assert "750" in panel._place_button.label  # payout(500, flat 1.5)


async def test_all_stake_arms_full_balance(fake_bot, interaction, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "draw"
    await panel.refresh()

    modal = _modal_with_stake(panel, "all")
    await modal.on_submit(interaction)

    assert fake_bot.db.place_calls == []
    assert panel.selected_stake == 10_000


# ── place button (commits at re-resolved odds) ───────────────────────────────

async def test_place_commits_with_flat_fallback_odds(fake_bot, interaction, clock):
    panel = await _armed_panel(fake_bot, outcome="away", stake=500)

    await panel._on_place_bet(interaction)

    assert fake_bot.db.place_calls == [{
        "user_id": USER_ID,
        "guild_id": GUILD_ID,
        "match_id": 1,
        "outcome": "away",
        "stake": 500,
        "odds": WCBET_ODDS,
    }]
    assert panel.balance == 9_500  # FakeDB.place_result
    assert panel.selected_match_id is None
    assert panel.selected_outcome is None
    assert panel.selected_stake is None
    assert panel.notice is not None and "750" in panel.notice
    assert interaction.response.edited


async def test_place_commits_at_live_odds(fake_bot, interaction, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _armed_panel(fake_bot, outcome="away", stake=500)

    await panel._on_place_bet(interaction)

    assert fake_bot.db.place_calls[0]["odds"] == Decimal("8.50")
    assert panel.notice is not None and "4,250" in panel.notice  # 500 * 8.50


async def test_place_after_kickoff_rejected(fake_bot, interaction, clock):
    panel = await _armed_panel(fake_bot, outcome="home", stake=500)

    clock["now"] = datetime(2026, 6, 11, 20, 0, tzinfo=UTC)  # match 1 started
    await panel._on_place_bet(interaction)

    assert fake_bot.db.place_calls == []
    assert panel.selected_match_id is None
    assert panel.notice is not None and "kicked off" in panel.notice


async def test_odds_drift_blocks_commit(fake_bot, interaction, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _armed_panel(fake_bot, outcome="away", stake=500)  # armed @ 8.50

    fake_odds[1] = MatchOdds(
        home=Decimal("1.50"), draw=Decimal("4.20"), away=Decimal("7.00"),
    )
    await panel._on_place_bet(interaction)

    assert fake_bot.db.place_calls == []  # refused
    assert panel.notice is not None and "Odds moved" in panel.notice
    # Re-armed at the new price; a second click commits.
    assert panel._armed_odds == Decimal("7.00")
    await panel._on_place_bet(interaction)
    assert fake_bot.db.place_calls[0]["odds"] == Decimal("7.00")


async def test_odds_fetch_blip_keeps_armed_price(fake_bot, interaction, clock, fake_odds):
    """A failed re-fetch must not silently reprice a real bet to flat 1.5."""
    fake_odds[1] = MATCH_1_ODDS
    panel = await _armed_panel(fake_bot, outcome="away", stake=500)  # armed @ 8.50

    fake_odds.clear()  # simulate ESPN returning no odds for this match
    await panel._on_place_bet(interaction)

    assert fake_bot.db.place_calls == []  # not committed at the flat fallback
    assert panel._armed_odds == Decimal("8.50")  # armed price preserved
    assert panel.notice is not None and "refresh" in panel.notice.lower()

    # Odds come back; a retry commits at the real price.
    fake_odds[1] = MATCH_1_ODDS
    await panel._on_place_bet(interaction)
    assert fake_bot.db.place_calls[0]["odds"] == Decimal("8.50")


async def test_flat_armed_bet_commits_despite_missing_odds(fake_bot, interaction, clock):
    """A bet armed at the flat fallback still commits when no line exists."""
    panel = await _armed_panel(fake_bot, outcome="away", stake=500)  # flat 1.5

    await panel._on_place_bet(interaction)

    assert fake_bot.db.place_calls[0]["odds"] == WCBET_ODDS


async def test_blip_surfaces_fallback_button(fake_bot, interaction, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _armed_panel(fake_bot, outcome="away", stake=500)  # armed @ 8.50
    assert panel._fallback_button is None  # no blip yet

    fake_odds.clear()  # ESPN blip
    await panel._on_place_bet(interaction)

    assert panel._odds_blip is True
    assert panel._fallback_button is not None
    assert str(WCBET_ODDS) in panel._fallback_button.label
    assert fake_bot.db.place_calls == []  # nothing committed yet


async def test_fallback_button_commits_at_flat_odds(fake_bot, interaction, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _armed_panel(fake_bot, outcome="away", stake=500)  # armed @ 8.50
    fake_odds.clear()
    await panel._on_place_bet(interaction)  # trips the blip guard

    await panel._on_place_fallback(interaction)

    assert fake_bot.db.place_calls[0]["odds"] == WCBET_ODDS  # conscious downgrade
    assert panel.selected_match_id is None  # stepper reset on success
    assert panel._odds_blip is False


async def test_blip_clears_on_successful_retry(fake_bot, interaction, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _armed_panel(fake_bot, outcome="away", stake=500)
    fake_odds.clear()
    await panel._on_place_bet(interaction)  # blip
    assert panel._odds_blip is True

    fake_odds[1] = MATCH_1_ODDS  # odds come back
    await panel._on_place_bet(interaction)  # retry commits at the real price

    assert fake_bot.db.place_calls[0]["odds"] == Decimal("8.50")
    assert panel._odds_blip is False
    assert panel._fallback_button is None


async def test_close_collapses_panel(fake_bot, interaction, clock):
    import discord

    panel = await _open_panel(fake_bot)
    await panel._on_close(interaction)

    assert panel.is_finished()  # view stopped
    assert interaction.response.edited  # message re-rendered
    text = "\n".join(
        item.content
        for item in panel.children[0].children
        if isinstance(item, discord.ui.TextDisplay)
    )
    assert "closed" in text.lower()


# ── panel rendering (step hint, focused card, bet slip) ─────────────────────

def _text(panel: views.BetPanelView) -> str:
    """Concatenate every TextDisplay in the panel's container."""
    import discord

    container = panel.children[0]
    return "\n".join(
        item.content
        for item in container.children
        if isinstance(item, discord.ui.TextDisplay)
    )


async def test_step_hint_tracks_progress(fake_bot, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _open_panel(fake_bot)
    assert "Step 1 of 3" in _text(panel)

    panel.selected_match_id = 1
    await panel.refresh()
    assert "Step 2 of 3" in _text(panel)

    panel.selected_outcome = "away"
    await panel.refresh()
    assert "Step 3 of 3" in _text(panel)

    panel.selected_stake = 500
    await panel.refresh()
    assert "Ready" in _text(panel)


async def test_match_list_collapses_to_focused_card(fake_bot, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _open_panel(fake_bot)
    # Pre-selection: both of today's matches are listed.
    text = _text(panel)
    assert "Mexico" in text and "South Korea" in text

    panel.selected_match_id = 1
    await panel.refresh()
    text = _text(panel)
    # Focused card for match 1 only; the other match drops out of the prose.
    assert "### " in text and "Mexico" in text
    assert "South Korea" not in text


async def test_bet_slip_summarises_selection(fake_bot, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "away"  # 8.50
    await panel.refresh()
    assert "Bet slip" in _text(panel)
    assert "add a stake" in _text(panel)

    panel.selected_stake = 500
    await panel.refresh()
    text = _text(panel)
    assert "Bet slip" in text
    assert "4,250" in text  # payout(500, 8.50)


# ── stepper state & pricing ──────────────────────────────────────────────────

async def test_stepper_gating(fake_bot, clock):
    panel = await _open_panel(fake_bot)

    assert panel._outcome_buttons  # built with today's fixtures present
    assert all(button.disabled for button in panel._outcome_buttons.values())
    assert panel._stake_select is not None and panel._stake_select.disabled
    assert panel._place_button is not None and panel._place_button.disabled

    panel.selected_match_id = 1
    await panel.refresh()
    assert not any(button.disabled for button in panel._outcome_buttons.values())
    assert panel._stake_select.disabled  # outcome still missing
    assert panel._place_button.disabled

    panel.selected_outcome = "draw"
    await panel.refresh()
    assert panel._outcome_buttons["draw"].style is ButtonStyle.success
    assert panel._outcome_buttons["home"].style is ButtonStyle.secondary
    assert not panel._stake_select.disabled
    assert panel._place_button.disabled  # stake still missing

    panel.selected_stake = 500
    await panel.refresh()
    assert not panel._place_button.disabled


async def test_outcome_buttons_show_live_prices(fake_bot, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    await panel.refresh()

    assert "1.43" in panel._outcome_buttons["home"].label
    assert "4.40" in panel._outcome_buttons["draw"].label
    assert "8.50" in panel._outcome_buttons["away"].label


async def test_stake_options_carry_payouts(fake_bot, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "away"  # 8.50
    await panel.refresh()

    labels = [option.label for option in panel._stake_select.options]
    assert "500 → pays 4,250" in labels
    assert any(label.startswith("All in (10,000)") for label in labels)
    assert labels[-1] == "Custom amount…"


async def test_outcome_change_reprices_stake_options(fake_bot, clock, fake_odds):
    fake_odds[1] = MATCH_1_ODDS
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "away"
    panel.selected_stake = 500
    await panel.refresh()
    assert "win 4,250" in panel._place_button.label

    panel.selected_outcome = "draw"  # 4.40 — stake kept, price changes
    await panel.refresh()
    assert panel.selected_stake == 500
    assert "win 2,200" in panel._place_button.label


async def test_refresh_resets_selection_when_match_kicks_off(fake_bot, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "home"
    panel.selected_stake = 500
    await panel.refresh()

    clock["now"] = datetime(2026, 6, 11, 20, 0, tzinfo=UTC)
    await panel.refresh()

    assert panel.selected_match_id is None
    assert panel.selected_outcome is None
    assert panel.selected_stake is None
    assert panel.notice is not None and "kicked off" in panel.notice
