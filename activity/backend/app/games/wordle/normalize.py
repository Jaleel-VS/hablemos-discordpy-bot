"""Spanish word normalization for Wordle.

The game is played over a 27-letter alphabet where **Ñ is a distinct letter**
but **accents are not** (á→a, é→e, í→i, ó→o, ú→u, ü→u). This is the de-facto
standard in shipped Spanish Wordle clones: players never need to type accents,
and the secret, the guess, and every dictionary entry are normalized
identically so comparisons line up.

The NFD trap: ``unicodedata.normalize("NFD", "ñ")`` decomposes ñ into ``n`` +
combining tilde, so a naive combining-mark strip would destroy ñ. We protect ñ
behind a sentinel first, strip marks, then restore it.
"""
import unicodedata

# A private-use codepoint that cannot occur in real input, used to shield ñ/Ñ
# from the combining-mark strip.
_SENTINEL = ""


def normalize(word: str) -> str:
    """Lowercase a word, strip accents, and preserve ñ as a single letter.

    Returns a string over the alphabet ``a-z`` plus ``ñ``. Non-letter
    characters are left to the caller to filter (see :func:`is_valid_shape`).
    """
    lowered = word.strip().lower()
    # Protect ñ before decomposition so its tilde isn't stripped as an accent.
    shielded = lowered.replace("ñ", _SENTINEL)
    decomposed = unicodedata.normalize("NFD", shielded)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace(_SENTINEL, "ñ")


def letters(word: str) -> list[str]:
    """Split a normalized word into letters, treating ñ as one character.

    Python already iterates ``"ñ"`` (a single normalized codepoint) as one
    character, so plain ``list()`` is correct here — this helper exists to make
    that intent explicit and to be the single place indexing lives.
    """
    return list(word)


# Length of a valid Wordle word, counted in normalized letters (ñ = 1).
WORD_LENGTH = 5

_ALLOWED = set("abcdefghijklmnopqrstuvwxyzñ")


def is_valid_shape(normalized: str) -> bool:
    """Whether a normalized word is exactly WORD_LENGTH allowed letters."""
    chars = letters(normalized)
    return len(chars) == WORD_LENGTH and all(c in _ALLOWED for c in chars)
