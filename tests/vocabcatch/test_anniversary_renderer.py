"""Anniversary card renderers (Sello stamp + Tinta ink) and article splitting."""
from collections.abc import Callable
from datetime import date
from io import BytesIO
from typing import TYPE_CHECKING, cast

import pytest
from PIL import Image, ImageChops, ImageStat

from cogs.vocabcatch_cog.anniversary_renderer import render_ink, render_stamp
from cogs.vocabcatch_cog.catch_logic import resolve_card, split_article
from cogs.vocabcatch_cog.config import (
    MODE_EN_TO_ES,
    MODE_ES_TO_EN,
    MODE_SHOW_ES,
)

if TYPE_CHECKING:
    from cogs.vocabcatch_cog.anniversary_renderer import AnniversaryCard

type Renderer = Callable[[dict, str, bool], BytesIO]

_CARD: dict = {
    "card_id": 13, "word_es": "la mariposa", "word_en": "the butterfly",
    "part_of_speech": "sustantivo", "gender": "la",
    "example_es": "Una mariposa se posó en la flor.",
    "example_en": "A butterfly landed on the flower.", "rarity": 3,
}


def _stamp(card: dict, mode: str, revealed: bool) -> BytesIO:
    return render_stamp(cast("AnniversaryCard", card), resolve_card(card, mode), revealed=revealed,
                        caught_on=date(2026, 10, 3))


def _ink(card: dict, mode: str, revealed: bool) -> BytesIO:
    return render_ink(cast("AnniversaryCard", card), resolve_card(card, mode), revealed=revealed)


_RENDERERS = [pytest.param(_stamp, id="sello"), pytest.param(_ink, id="tinta")]


def _png(buf: BytesIO) -> Image.Image:
    img = Image.open(buf)
    assert img.format == "PNG"
    return img


@pytest.mark.parametrize("render", _RENDERERS)
@pytest.mark.parametrize("mode", [MODE_SHOW_ES, MODE_EN_TO_ES, MODE_ES_TO_EN])
@pytest.mark.parametrize("revealed", [False, True])
def test_renders_card_size_rgba_every_mode(render: Renderer, mode: str, revealed: bool) -> None:
    img = _png(render(_CARD, mode, revealed))
    assert img.size == (360, 504)
    assert img.mode == "RGBA"


@pytest.mark.parametrize("render", _RENDERERS)
def test_pattern_is_seeded_by_card_id(render: Renderer) -> None:
    # Only paper grain is random, so re-rendering a card stays far closer
    # than rendering the same word under another card_id.
    def mean_diff(a: dict, b: dict) -> float:
        x = _png(render(a, MODE_SHOW_ES, False)).convert("RGB")
        y = _png(render(b, MODE_SHOW_ES, False)).convert("RGB")
        return sum(ImageStat.Stat(ImageChops.difference(x, y)).mean)

    assert mean_diff(_CARD, _CARD) < mean_diff(_CARD, {**_CARD, "card_id": 99})


@pytest.mark.parametrize("render", _RENDERERS)
def test_missing_optional_fields_and_long_words(render: Renderer) -> None:
    card = {
        **_CARD, "word_es": "electroencefalografista", "word_en": "electroencephalographer",
        "part_of_speech": None, "gender": None, "example_es": None,
        "example_en": "An extremely long example sentence that keeps going well past the width of any card.",
    }
    for mode in (MODE_SHOW_ES, MODE_EN_TO_ES):
        for revealed in (False, True):
            assert _png(render(card, mode, revealed)).size == (360, 504)


@pytest.mark.parametrize(("word", "lang", "expected"), [
    ("la casa", "es", ("la", "casa")),
    ("El Perro", "es", ("El", "Perro")),
    ("the house", "en", ("the", "house")),
    ("comer", "es", ("", "comer")),
    ("the house", "es", ("", "the house")),  # English article in Spanish
    ("la casa blanca", "es", ("", "la casa blanca")),  # phrases stay whole
])
def test_split_article(word: str, lang: str, expected: tuple[str, str]) -> None:
    assert split_article(word, lang) == expected
