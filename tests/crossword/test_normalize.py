"""Tests for the _normalize helper.

Ensures Spanish accent handling and punctuation stripping are symmetric
so that try_solve matches user input regardless of diacritics.
"""
from __future__ import annotations

from cogs.crossword_cog.main import _normalize


def test_strips_accents() -> None:
    assert _normalize("canción") == _normalize("cancion")
    assert _normalize("ÁRBOL") == "arbol"


def test_case_insensitive() -> None:
    assert _normalize("Casa") == _normalize("CASA") == "casa"


def test_trims_whitespace_and_punctuation() -> None:
    assert _normalize("  ¡hola! ") == "hola"
    assert _normalize("un-dos") == "undos"


def test_empty_after_normalization() -> None:
    assert _normalize("   ") == ""
    assert _normalize("¿¡!?") == ""


def test_numbers_preserved() -> None:
    # Normalizer strips non-alnum; digits stay.
    assert _normalize("2024!") == "2024"


def test_n_tilde_collapses_to_n() -> None:
    # Spanish ñ in practice: "año" → "ano". Documents current behavior
    # so regressions are intentional.
    assert _normalize("año") == "ano"
