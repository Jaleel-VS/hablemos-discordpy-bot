"""Spanish syllable splitting and stress detection for card typography.

Pure, rule-based (RAE orthographic rules), no dependencies:

- ``ch``, ``ll``, ``rr`` are single consonants; ``qu``/``gu`` before
  ``e``/``i`` are one consonant (the ``u`` is silent); ``ü`` is a vowel.
- ``y`` is a vowel only word-finally or before a consonant (``rey``,
  ``muy``); otherwise it is a consonant (``ayer``, ``yo``).
- Two strong vowels (``a e o``, or an accented ``í``/``ú``) side by side
  form a hiatus (separate syllables): ``dí·a``, ``re·ír``, ``a·é·re·o``.
  Any other vowel sequence is a diphthong/triphthong (``ciu·dad``, ``buey``).
- Between vowels, one consonant starts the next syllable; a cluster
  keeps an inseparable pair (``pr``, ``bl``, ``tr``…) together at the
  start of the next syllable and splits everything else before its last
  consonant.

Stress: the syllable with a written accent; otherwise the penultimate
syllable for words ending in a vowel, ``n`` or ``s``, else the last.
"""
from dataclasses import dataclass

_STRONG = frozenset("aeoáéóíú")  # accented í/ú behave as strong (hiatus)
_WEAK = frozenset("iuüy")
_VOWELS = _STRONG | _WEAK
_ACCENTED = frozenset("áéíóú")
_FRONT = frozenset("eéií")
_INSEPARABLE = frozenset({
    "pr", "br", "tr", "dr", "cr", "kr", "gr", "fr",
    "pl", "bl", "cl", "kl", "gl", "fl",
})


@dataclass(frozen=True, slots=True)
class _Tok:
    text: str       # original-case slice of the word
    vowel: bool


def _tokenize(word: str) -> list[_Tok]:
    low = word.lower()
    n = len(low)
    out: list[_Tok] = []
    i = 0
    while i < n:
        two = low[i:i + 2]
        if two in ("ch", "ll", "rr") or (
            two in ("qu", "gu") and i + 2 < n and low[i + 2] in _FRONT
        ):
            out.append(_Tok(word[i:i + 2], vowel=False))
            i += 2
            continue
        ch = low[i]
        if ch == "y":
            is_vowel = i == n - 1 or low[i + 1] not in _VOWELS
        else:
            is_vowel = ch in _VOWELS
        out.append(_Tok(word[i], vowel=is_vowel))
        i += 1
    return out


def _is_strong(tok: _Tok) -> bool:
    return tok.text.lower() in _STRONG


def _split_cluster(cluster: list[_Tok]) -> int:
    """Index where a consonant cluster between two vowels splits."""
    n = len(cluster)
    if n <= 1:
        return 0
    pair = (cluster[-2].text + cluster[-1].text).lower()
    return n - 2 if pair in _INSEPARABLE else n - 1


def syllabify(word: str) -> list[str]:
    """Split one Spanish word into syllables, preserving the original case.

    Returns ``[word]`` for input with no vowel (e.g. ``"sh"``) or
    containing whitespace — callers render multi-word entries unsplit.
    """
    if not word or any(ch.isspace() for ch in word):
        return [word]
    toks = _tokenize(word)

    # Alternate consonant clusters and vowel nuclei, splitting hiatus.
    clusters: list[list[_Tok]] = [[]]
    nuclei: list[list[_Tok]] = []
    for tok in toks:
        if not tok.vowel:
            clusters[-1].append(tok)
            continue
        prev_is_vowel = bool(nuclei) and not clusters[-1]
        if prev_is_vowel and not (_is_strong(nuclei[-1][-1]) and _is_strong(tok)):
            nuclei[-1].append(tok)
        else:
            nuclei.append([tok])
            clusters.append([])
    if not nuclei:
        return [word]

    sylls = ["".join(t.text for t in clusters[0] + nuclei[0])]
    for j in range(1, len(nuclei)):
        between = clusters[j]
        cut = _split_cluster(between)
        sylls[-1] += "".join(t.text for t in between[:cut])
        sylls.append("".join(t.text for t in between[cut:] + nuclei[j]))
    sylls[-1] += "".join(t.text for t in clusters[len(nuclei)])
    return sylls


def stressed_index(syllables: list[str]) -> int:
    """Index of the stressed syllable (written accent, else RAE default)."""
    for i, syl in enumerate(syllables):
        if any(ch in _ACCENTED for ch in syl.lower()):
            return i
    if len(syllables) < 2:
        return 0
    last = syllables[-1].lower()[-1:]
    return len(syllables) - 2 if last in "aeiouns" else len(syllables) - 1
