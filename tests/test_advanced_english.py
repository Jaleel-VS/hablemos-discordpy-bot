"""English catalog and native-language/translation behavior for the shared browser."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.advanced_english_cog.main import DATA_DIR
from cogs.advanced_spanish_cog.main import DATA_DIR as SPANISH_DATA_DIR
from cogs.utils.vocabulary import (
    VocabularyEntry,
    VocabularyView,
    find_entries,
    load_catalog,
)


@pytest.fixture(scope="module")
def catalog() -> tuple[VocabularyEntry, ...]:
    """Load the English catalog used by the real command."""
    return load_catalog(DATA_DIR)


def _text(view: VocabularyView) -> str:
    return "\n".join(item.content for item in view.walk_children() if isinstance(item, discord.ui.TextDisplay))


async def test_english_catalog_has_complete_readable_cards(catalog: tuple[VocabularyEntry, ...]) -> None:
    assert len(catalog) >= 400
    for entry in catalog:
        assert entry.meaning_en != entry.meaning_es
        assert len({example.en for example in entry.examples}) == 2
        assert len({example.es for example in entry.examples}) == 2
        assert all(example.en != example.es for example in entry.examples)
        view = VocabularyView((entry,), 1, language="en")
        assert len(_text(view)) <= 4000, entry.term
        assert view.has_components_v2()
        view.stop()


def test_acerbic_and_case_insensitive_fragment_search(catalog: tuple[VocabularyEntry, ...]) -> None:
    exact = find_entries(catalog, "  ACERBIC  ")
    assert [entry.term for entry in exact] == ["acerbic"]
    assert exact[0] in find_entries(catalog, "acerb")
    assert find_entries(catalog, "zzzznotanenglishword") == ()


async def test_english_card_hides_spanish_without_affecting_spanish_browser(catalog: tuple[VocabularyEntry, ...]) -> None:
    entry = find_entries(catalog, "acerbic")[0]
    view = VocabularyView((entry,), 1, language="en")
    spanish_entry = find_entries(load_catalog(SPANISH_DATA_DIR), "explayarse")[0]
    spanish_view = VocabularyView((spanish_entry,), 1, language="es")
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    try:
        initial = _text(view)
        assert initial.index(entry.meaning_en) < initial.index(entry.meaning_es)
        spanish_initial = _text(spanish_view)
        await view._toggle_translation(interaction)
        visible = _text(view)
        assert entry.meaning_en in visible
        assert entry.meaning_es not in visible
        assert all(example.en in visible and example.es not in visible for example in entry.examples)
        assert entry.note in visible
        assert _text(spanish_view) == spanish_initial
        await view._toggle_translation(interaction)
        assert entry.meaning_es in _text(view)
    finally:
        view.stop()
        spanish_view.stop()
