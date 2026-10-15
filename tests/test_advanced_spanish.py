"""Advanced vocabulary data quality, search, visibility, and browser behavior."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands

from cogs.advanced_english_cog.main import AdvancedEnglish
from cogs.advanced_spanish_cog.main import DATA_DIR, AdvancedSpanish
from cogs.utils.vocabulary import (
    VocabularyEntry,
    VocabularyView,
    find_entries,
    load_catalog,
)


@pytest.fixture(scope="module")
def catalog() -> tuple[VocabularyEntry, ...]:
    """Load the same catalog used by the production command."""
    return load_catalog(DATA_DIR)


def _interaction(user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        edit_original_response=AsyncMock(),
    )


def _text(view: VocabularyView) -> str:
    return "\n".join(item.content for item in view.walk_children() if isinstance(item, discord.ui.TextDisplay))


def test_catalog_has_distinct_bilingual_examples(catalog: tuple[VocabularyEntry, ...]) -> None:
    """The extensive catalog must not pad cards with duplicated examples."""
    assert len(catalog) >= 400
    for entry in catalog:
        assert entry.meaning_es != entry.meaning_en
        assert len({example.es for example in entry.examples}) == 2
        assert len({example.en for example in entry.examples}) == 2
        assert all(example.es != example.en for example in entry.examples)


def test_search_accents_case_fragments_and_no_match(catalog: tuple[VocabularyEntry, ...]) -> None:
    assert [entry.term for entry in find_entries(catalog, "  AHINCO  ")] == ["ahínco"]
    assert [entry.term for entry in find_entries(catalog, "explay")] == ["explayarse"]
    assert find_entries(catalog, " ") == catalog
    assert find_entries(catalog, "zzzznotaword") == ()


async def test_cards_fit_discord_limits(catalog: tuple[VocabularyEntry, ...]) -> None:
    """Every complete bilingual card must fit Discord's V2 content budget."""
    for entry in catalog:
        view = VocabularyView((entry,), 1, language="es")
        assert len(_text(view)) <= 4000, entry.term
        assert view.has_components_v2()
        view.stop()


async def test_browsing_preserves_order_and_english_toggle(catalog: tuple[VocabularyEntry, ...]) -> None:
    deck = find_entries(catalog, "explayarse") + find_entries(catalog, "resquemor")
    view = VocabularyView(deck, 1, language="es")
    try:
        first = deck[0]
        assert first.meaning_en in _text(view)
        await view._toggle_translation(_interaction())
        assert first.meaning_es in _text(view)
        assert first.meaning_en not in _text(view)
        assert all(example.en not in _text(view) for example in first.examples)
        await view._next(_interaction())
        assert view.index == 1 and not view.show_translation
        assert deck[1].meaning_es in _text(view)
        await view._next(_interaction())
        assert view.index == 1
        await view._previous(_interaction())
        assert view.index == 0 and first.meaning_es in _text(view)
        await view._previous(_interaction())
        assert view.index == 0
        await view._toggle_translation(_interaction())
        assert first.meaning_en in _text(view)
    finally:
        view.stop()


async def test_only_invoker_controls_browser(catalog: tuple[VocabularyEntry, ...]) -> None:
    view = VocabularyView(catalog[:2], 1, language="es")
    try:
        other = _interaction(2)
        assert not await view.interaction_check(other)
        assert other.response.send_message.call_args.kwargs["ephemeral"]
        assert await view.interaction_check(_interaction(1))
    finally:
        view.stop()


async def test_failed_edit_does_not_advance_browser(catalog: tuple[VocabularyEntry, ...]) -> None:
    view = VocabularyView(catalog[:2], 1, language="es")
    interaction = _interaction()
    interaction.edit_original_response.side_effect = discord.HTTPException(
        SimpleNamespace(status=500, reason="Server error"), "Unavailable",
    )
    original = _text(view)
    try:
        with pytest.raises(discord.HTTPException):
            await view._next(interaction)
        assert view.index == 0
        assert _text(view) == original
    finally:
        view.stop()


async def test_timeout_keeps_card_readable_and_freezes_controls(catalog: tuple[VocabularyEntry, ...]) -> None:
    view = VocabularyView(catalog[:2], 1, language="es")
    view.message = SimpleNamespace(edit=AsyncMock())
    try:
        await view.on_timeout()
        assert catalog[0].meaning_es in _text(view)
        controls = [item for item in view.walk_children() if isinstance(item, discord.ui.Button) and item.url is None]
        assert all(button.disabled for button in controls)
        await view._next(_interaction())
        assert view.index == 0
    finally:
        view.stop()


@pytest.mark.parametrize("cog_type", [AdvancedSpanish, AdvancedEnglish])
async def test_slash_cooldown_is_per_user_and_expires(cog_type: type) -> None:
    async with commands.Bot(command_prefix="$", intents=discord.Intents.none(), help_command=None) as bot:
        cog = cog_type(bot)
        await bot.add_cog(cog)
        command = cog.vocabulary
        interaction = _interaction()
        interaction.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        interaction.response.is_done = lambda: False
        assert await command._check_can_run(interaction)
        with pytest.raises(discord.app_commands.CommandOnCooldown) as caught:
            await command._check_can_run(interaction)
        await cog.cog_app_command_error(interaction, caught.value)
        interaction.response.send_message.assert_awaited_once()
        assert interaction.response.send_message.call_args.kwargs["ephemeral"]

        another_reader = _interaction(user_id=2)
        another_reader.created_at = interaction.created_at
        assert await command._check_can_run(another_reader)

        interaction.created_at += timedelta(seconds=6)
        assert await command._check_can_run(interaction)
