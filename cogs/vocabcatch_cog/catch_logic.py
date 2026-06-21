"""Pure logic for Vocab Catch — no Discord/DB types, fully unit-testable.

Holds:
- answer-matching normalization (accent + case folding so ``catch nino``
  catches ``niño``),
- the rarity → points lookup,
- the channel-**mode** resolver that turns a bidirectional card into a
  one-directional view (what to show vs. what to type).
"""
import unicodedata
from typing import TypedDict

from .config import (
    MODE_EN_TO_ES,
    MODE_ES_TO_EN,
    RARITY_POINTS,
)

# Spanish articles that may be dropped when catching a Spanish answer.
_ES_ARTICLES = {"el", "la", "los", "las", "un", "una", "unos", "unas"}
# English articles that may be dropped when catching an English answer.
_EN_ARTICLES = {"a", "an", "the"}


class CardView(TypedDict):
    """A card resolved for one channel direction (what to render/accept)."""

    prompt: str          # word shown on the card
    answer: str          # word the player must type to catch
    prompt_lang: str     # 'es' | 'en' — language of the shown word
    answer_lang: str     # 'es' | 'en' — language of the answer
    example: str | None  # example sentence in the prompt language


def normalize_answer(text: str) -> str:
    """Fold a guess/word for comparison: strip accents, casefold, collapse ws."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def answer_matches(guess: str, answer: str, *, answer_lang: str = "es") -> bool:
    """True when ``guess`` matches ``answer`` (accent/case/article-tolerant).

    Accepts the full word or the bare noun without its leading article,
    using the article set for ``answer_lang``.
    """
    g = normalize_answer(guess)
    a = normalize_answer(answer)
    if not g:
        return False
    if g == a:
        return True
    parts = a.split()
    articles = _EN_ARTICLES if answer_lang == "en" else _ES_ARTICLES
    if len(parts) == 2 and parts[0] in articles:
        return g == parts[1]
    return False


def resolve_card(card: dict, mode: str) -> CardView:
    """Resolve a bidirectional card into a one-directional view for ``mode``.

    - ``en_to_es``: show English, answer in Spanish.
    - ``es_to_en``: show Spanish, answer in English.
    - anything else (``show_es``): show Spanish, answer in Spanish.
    """
    es, en = card["word_es"], card["word_en"]
    ex_es, ex_en = card.get("example_es"), card.get("example_en")
    if mode == MODE_EN_TO_ES:
        return CardView(prompt=en, answer=es, prompt_lang="en", answer_lang="es",
                        example=ex_en)
    if mode == MODE_ES_TO_EN:
        return CardView(prompt=es, answer=en, prompt_lang="es", answer_lang="en",
                        example=ex_es)
    # MODE_SHOW_ES (neutral): show + answer in Spanish.
    return CardView(prompt=es, answer=es, prompt_lang="es", answer_lang="es",
                    example=ex_es)


def points_for(rarity: int) -> int:
    """Points awarded for catching a card of the given rarity tier."""
    return RARITY_POINTS.get(int(rarity), 0)
