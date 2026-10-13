"""Advanced vocabulary data quality, search, visibility, and browser behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands

from cogs.advanced_spanish_cog.catalog import (
    VocabularyEntry,
    find_entries,
    load_catalog,
)
from cogs.advanced_spanish_cog.main import AdvancedSpanish, VocabularyView
from cogs.general_cog.main import _collect_cog_entries


@pytest.fixture(scope="module")
def catalog() -> tuple[VocabularyEntry, ...]:
    """Load the same catalog used by the production command."""
    return load_catalog()


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
        view = VocabularyView((entry,), 1)
        assert len(_text(view)) <= 4000, entry.term
        assert view.has_components_v2()
        view.stop()


async def test_browsing_preserves_order_and_english_toggle(catalog: tuple[VocabularyEntry, ...]) -> None:
    deck = find_entries(catalog, "explayarse") + find_entries(catalog, "resquemor")
    view = VocabularyView(deck, 1)
    try:
        first = deck[0]
        assert first.meaning_en in _text(view)
        await view._toggle_english(_interaction())
        assert first.meaning_es in _text(view)
        assert first.meaning_en not in _text(view)
        assert all(example.en not in _text(view) for example in first.examples)
        await view._next(_interaction())
        assert view.index == 1 and not view.show_english
        assert deck[1].meaning_es in _text(view)
        await view._next(_interaction())
        assert view.index == 1
        await view._previous(_interaction())
        assert view.index == 0 and first.meaning_es in _text(view)
        await view._previous(_interaction())
        assert view.index == 0
        await view._toggle_english(_interaction())
        assert first.meaning_en in _text(view)
    finally:
        view.stop()


async def test_only_invoker_controls_browser(catalog: tuple[VocabularyEntry, ...]) -> None:
    view = VocabularyView(catalog[:2], 1)
    try:
        other = _interaction(2)
        assert not await view.interaction_check(other)
        assert other.response.send_message.call_args.kwargs["ephemeral"]
        assert await view.interaction_check(_interaction(1))
    finally:
        view.stop()


async def test_failed_edit_does_not_advance_browser(catalog: tuple[VocabularyEntry, ...]) -> None:
    view = VocabularyView(catalog[:2], 1)
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
    view = VocabularyView(catalog[:2], 1)
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


async def test_hidden_vocabulary_is_callable_but_absent_from_public_help() -> None:
    class VisibleCog(commands.Cog):
        @commands.command()
        async def visible(self, ctx: commands.Context) -> None:
            """A public command to ensure help still lists visible commands."""
            await ctx.send("Public command")

    async with commands.Bot(command_prefix="$", intents=discord.Intents.none(), help_command=None) as bot:
        await bot.add_cog(AdvancedSpanish(bot))
        await bot.add_cog(VisibleCog())
        command = bot.get_command("c")
        assert command is not None and command.hidden
        entries = _collect_cog_entries(bot)
        assert [entry[0] for entry in entries] == ["VisibleCog"]
