"""Tests for native-language role colors in multi-message quotes."""

from types import SimpleNamespace

from cogs.quote_generator_cog.config import (
    ROLE_COLOR_ENGLISH_NATIVE,
    ROLE_COLOR_OTHER_NATIVE,
    ROLE_COLOR_SPANISH_NATIVE,
    ROLE_ID_ENGLISH_NATIVE,
    ROLE_ID_OTHER_NATIVE,
    ROLE_ID_SPANISH_NATIVE,
)
from cogs.quote_generator_cog.main import QuoteGenerator


def _member(*role_ids: int) -> SimpleNamespace:
    return SimpleNamespace(roles=[SimpleNamespace(id=role_id) for role_id in role_ids])


def test_quotem_uses_spanish_color_first_when_multiple_native_roles_match() -> None:
    member = _member(ROLE_ID_ENGLISH_NATIVE, ROLE_ID_OTHER_NATIVE, ROLE_ID_SPANISH_NATIVE)

    assert QuoteGenerator._quotem_username_color(member) == ROLE_COLOR_SPANISH_NATIVE


def test_quotem_uses_other_native_color() -> None:
    assert QuoteGenerator._quotem_username_color(_member(ROLE_ID_OTHER_NATIVE)) == ROLE_COLOR_OTHER_NATIVE


def test_quotem_uses_english_native_color() -> None:
    assert QuoteGenerator._quotem_username_color(_member(ROLE_ID_ENGLISH_NATIVE)) == ROLE_COLOR_ENGLISH_NATIVE


def test_quotem_leaves_unmatched_members_neutral() -> None:
    assert QuoteGenerator._quotem_username_color(_member(999)) is None
