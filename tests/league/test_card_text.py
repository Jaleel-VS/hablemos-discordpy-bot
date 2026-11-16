"""Cards use the language the reader is learning."""
from cogs.league_cog.card_text import EN, ES, card_text_for
from cogs.utils.guild import LEARNING_ENGLISH_ROLE_ID, LEARNING_SPANISH_ROLE_ID


def test_spanish_learners_get_spanish_everyone_else_english() -> None:
    assert card_text_for({LEARNING_SPANISH_ROLE_ID, 1}) is ES
    assert card_text_for({LEARNING_ENGLISH_ROLE_ID}) is EN
    assert card_text_for({LEARNING_SPANISH_ROLE_ID, LEARNING_ENGLISH_ROLE_ID}) is EN
    assert card_text_for(set()) is EN


def test_streak_line_handles_none_one_and_many() -> None:
    assert ES.streak_line(0, 4) == "Sin racha activa  ·  récord 4"
    assert ES.streak_line(1, 4) == "Racha de 1 día  ·  récord 4"
    assert EN.streak_line(5, 12) == "5-day streak  ·  best 12"
