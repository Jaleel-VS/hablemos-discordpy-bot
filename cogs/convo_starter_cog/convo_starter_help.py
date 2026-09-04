"""Backward-compatible conversation-starter helpers.

New code should import from :mod:`cogs.convo_starter_cog.questions`.
"""

from random import choice

from cogs.convo_starter_cog.questions import (
    CATEGORY_DESCRIPTIONS,
    load_questions,
    resolve_category,
)

categories = list(CATEGORY_DESCRIPTIONS)


def get_random_question(category: str) -> tuple[str, str]:
    """Return a random pair for callers of the legacy helper."""
    questions = load_questions()
    return choice(questions[resolve_category(category)])


__all__ = ["categories", "get_random_question"]
