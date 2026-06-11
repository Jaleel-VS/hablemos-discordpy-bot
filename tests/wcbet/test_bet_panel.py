"""Tests for the betting panel views — stake validation, kickoff races,
and stepper button state. Pure-logic coverage lives in test_betting.py."""
from datetime import UTC, datetime

from discord import ButtonStyle

from cogs.wcbet_cog import views
from cogs.wcbet_cog.config import WCBET_ODDS

from .conftest import GUILD_ID, USER_ID


async def _open_panel(fake_bot) -> views.BetPanelView:
    panel = views.BetPanelView(
        fake_bot, user_id=USER_ID, guild_id=GUILD_ID, balance=10_000,
    )
    await panel.refresh()
    return panel


def _modal_with_stake(panel: views.BetPanelView, raw: str) -> views.StakeModal:
    modal = views.StakeModal(panel)
    modal.stake_input._value = raw  # what discord fills in from the submit payload
    return modal


async def test_invalid_stake_rejected_without_db_call(fake_bot, interaction, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "home"
    await panel.refresh()

    modal = _modal_with_stake(panel, "not-a-number")
    await modal.on_submit(interaction)

    assert fake_bot.db.place_calls == []
    assert panel.notice is not None
    assert interaction.response.edited  # panel re-rendered with the notice


async def test_stake_submit_after_kickoff_rejected(fake_bot, interaction, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1  # kickoff 2026-06-11 19:00 UTC
    panel.selected_outcome = "home"
    await panel.refresh()

    modal = _modal_with_stake(panel, "500")
    clock["now"] = datetime(2026, 6, 11, 20, 0, tzinfo=UTC)  # match 1 started
    await modal.on_submit(interaction)

    assert fake_bot.db.place_calls == []
    assert panel.selected_match_id is None
    assert panel.selected_outcome is None
    assert panel.notice is not None and "kicked off" in panel.notice


async def test_valid_stake_places_bet(fake_bot, interaction, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "away"
    await panel.refresh()

    modal = _modal_with_stake(panel, "500")
    await modal.on_submit(interaction)

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
    assert panel.notice is not None and "750" in panel.notice  # payout(500)
    assert interaction.response.edited


async def test_all_stake_uses_full_balance(fake_bot, interaction, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "draw"
    await panel.refresh()

    modal = _modal_with_stake(panel, "all")
    await modal.on_submit(interaction)

    assert len(fake_bot.db.place_calls) == 1
    assert fake_bot.db.place_calls[0]["stake"] == 10_000


async def test_outcome_buttons_disabled_until_match_selected(fake_bot, clock):
    panel = await _open_panel(fake_bot)

    assert panel._outcome_buttons  # built with today's fixtures present
    assert all(button.disabled for button in panel._outcome_buttons.values())
    assert panel._place_button is not None and panel._place_button.disabled

    panel.selected_match_id = 1
    await panel.refresh()
    assert not any(button.disabled for button in panel._outcome_buttons.values())
    assert panel._place_button.disabled  # outcome still missing

    panel.selected_outcome = "draw"
    await panel.refresh()
    assert panel._outcome_buttons["draw"].style is ButtonStyle.success
    assert panel._outcome_buttons["home"].style is ButtonStyle.secondary
    assert not panel._place_button.disabled


async def test_refresh_resets_selection_when_match_kicks_off(fake_bot, clock):
    panel = await _open_panel(fake_bot)
    panel.selected_match_id = 1
    panel.selected_outcome = "home"
    await panel.refresh()

    clock["now"] = datetime(2026, 6, 11, 20, 0, tzinfo=UTC)
    await panel.refresh()

    assert panel.selected_match_id is None
    assert panel.selected_outcome is None
    assert panel.notice is not None and "kicked off" in panel.notice
