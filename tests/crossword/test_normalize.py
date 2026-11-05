"""Crossword identity ignores case, punctuation and Spanish diacritics."""
from __future__ import annotations

from cogs.crossword_cog.words import normalize_word


def test_strips_accents() -> None:
    assert normalize_word("canción") == normalize_word("cancion")
    assert normalize_word("ÁRBOL") == "arbol"


def test_case_insensitive() -> None:
    assert normalize_word("Casa") == normalize_word("CASA") == "casa"


def test_trims_whitespace_and_punctuation() -> None:
    assert normalize_word("  ¡hola! ") == "hola"
    assert normalize_word("un-dos") == "undos"


def test_empty_after_normalization() -> None:
    assert normalize_word("   ") == ""
    assert normalize_word("¿¡!?") == ""


def test_numbers_preserved() -> None:
    assert normalize_word("2024!") == "2024"


def test_n_tilde_collapses_to_n() -> None:
    assert normalize_word("año") == "ano"
