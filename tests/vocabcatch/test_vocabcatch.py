"""Tests for Vocab Catch pure logic (`cogs.vocabcatch_cog.catch_logic`)
and the card renderer smoke path. No Discord/DB needed."""
from cogs.vocabcatch_cog.catch_logic import (
    answer_matches,
    normalize_answer,
    points_for,
    resolve_card,
)
from cogs.vocabcatch_cog.config import (
    BEGINNER_RARITY_WEIGHTS,
    GENERAL_RARITY_WEIGHTS,
    MODE_EN_TO_ES,
    MODE_ES_TO_EN,
    MODE_SHOW_ES,
    RARITY_POINTS,
    weights_for_mode,
)
from cogs.vocabcatch_cog.renderer import render_card

_CARD = {
    "card_id": 7,
    "word_es": "el relámpago",
    "word_en": "lightning",
    "part_of_speech": "sustantivo",
    "gender": "el",
    "example_es": "El relámpago iluminó el cielo nocturno.",
    "example_en": "The lightning lit up the night sky.",
    "rarity": 4,
}


# ── normalize_answer ─────────────────────────────────────────────────────────

def test_normalize_strips_accents_and_case() -> None:
    assert normalize_answer("  El Niño ") == "el nino"
    assert normalize_answer("RELÁMPAGO") == "relampago"
    assert normalize_answer("corazón") == "corazon"


def test_normalize_collapses_whitespace() -> None:
    assert normalize_answer("el   gran  perro") == "el gran perro"


# ── answer_matches (Spanish answers) ─────────────────────────────────────────

def test_match_exact_and_accentless() -> None:
    assert answer_matches("el relámpago", "el relámpago")
    assert answer_matches("el relampago", "el relámpago")
    assert answer_matches("RELÁMPAGO", "el relámpago")  # article-dropped + case


def test_match_drops_leading_spanish_article() -> None:
    assert answer_matches("nino", "el niño")
    assert answer_matches("casa", "la casa")


def test_match_rejects_wrong_or_partial() -> None:
    assert not answer_matches("gato", "el perro")
    assert not answer_matches("", "el perro")
    assert not answer_matches("perr", "el perro")
    assert not answer_matches("el", "el relámpago")  # article-only


# ── answer_matches (English answers) ─────────────────────────────────────────

def test_match_drops_leading_english_article() -> None:
    assert answer_matches("house", "the house", answer_lang="en")
    assert answer_matches("THE HOUSE", "the house", answer_lang="en")
    assert answer_matches("dog", "the dog", answer_lang="en")


def test_english_article_not_dropped_in_spanish_mode() -> None:
    # 'the' is not a Spanish article, so 'house' shouldn't match 'the house'
    # when answer_lang defaults to Spanish.
    assert not answer_matches("house", "the house")


# ── resolve_card (channel modes) ─────────────────────────────────────────────

def test_resolve_en_to_es_shows_english_answers_spanish() -> None:
    v = resolve_card(_CARD, MODE_EN_TO_ES)
    assert v["prompt"] == "lightning" and v["prompt_lang"] == "en"
    assert v["answer"] == "el relámpago" and v["answer_lang"] == "es"
    assert v["example"] == _CARD["example_en"]


def test_resolve_es_to_en_shows_spanish_answers_english() -> None:
    v = resolve_card(_CARD, MODE_ES_TO_EN)
    assert v["prompt"] == "el relámpago" and v["prompt_lang"] == "es"
    assert v["answer"] == "lightning" and v["answer_lang"] == "en"
    assert v["example"] == _CARD["example_es"]


def test_resolve_show_es_is_neutral_spanish() -> None:
    v = resolve_card(_CARD, MODE_SHOW_ES)
    assert v["prompt"] == "el relámpago" == v["answer"]
    assert v["prompt_lang"] == v["answer_lang"] == "es"


# ── weights / points ─────────────────────────────────────────────────────────

def test_general_weights_steeper_than_beginner() -> None:
    # General should surface rares more than beginner channels.
    assert GENERAL_RARITY_WEIGHTS[5] > BEGINNER_RARITY_WEIGHTS[5]
    assert GENERAL_RARITY_WEIGHTS[3] > BEGINNER_RARITY_WEIGHTS[3]
    assert weights_for_mode(MODE_SHOW_ES) == GENERAL_RARITY_WEIGHTS
    assert weights_for_mode(MODE_EN_TO_ES) == BEGINNER_RARITY_WEIGHTS


def test_all_channels_can_spawn_all_rarities() -> None:
    # Every tier must have a non-zero weight in every channel kind.
    for weights in (BEGINNER_RARITY_WEIGHTS, GENERAL_RARITY_WEIGHTS):
        assert all(weights.get(t, 0) > 0 for t in (1, 2, 3, 4, 5))


def test_points_for_each_tier() -> None:
    for tier, pts in RARITY_POINTS.items():
        assert points_for(tier) == pts
    assert points_for(99) == 0
    assert points_for(5) > points_for(1)


# ── renderer smoke (all rarities, both states, each mode) ────────────────────

def test_render_produces_png_all_rarities_and_modes() -> None:
    for rarity in (1, 2, 3, 4, 5):
        card = {**_CARD, "rarity": rarity}
        for mode in (MODE_SHOW_ES, MODE_EN_TO_ES, MODE_ES_TO_EN):
            view = resolve_card(card, mode)
            for revealed in (False, True):
                data = render_card(card, view, revealed=revealed).getvalue()
                assert data[:8] == b"\x89PNG\r\n\x1a\n"
                assert len(data) > 1000


def test_render_handles_missing_optional_fields() -> None:
    minimal = {
        "card_id": 1, "word_es": "agua", "word_en": "water",
        "part_of_speech": None, "gender": None,
        "example_es": None, "example_en": None, "rarity": 1,
    }
    view = resolve_card(minimal, MODE_ES_TO_EN)
    assert render_card(minimal, view, revealed=True).getvalue()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_long_word_does_not_crash() -> None:
    card = {**_CARD, "word_es": "electroencefalografista", "rarity": 5}
    view = resolve_card(card, MODE_SHOW_ES)
    assert render_card(card, view, revealed=True).getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
