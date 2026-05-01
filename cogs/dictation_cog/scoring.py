"""Dictation scoring — fuzzy word-by-word comparison with accent forgiveness.

Max score: 4.  Deductions are proportional to the number of words.
"""

import re
import unicodedata

# Accent pairs: stripped form → accented forms that are "close enough"
_ACCENT_MAP: dict[str, str] = {
    "a": "áàâã", "e": "éèêë", "i": "íìîï",
    "o": "óòôõ", "u": "úùûü", "n": "ñ",
}


def _strip_accents(text: str) -> str:
    """Remove combining diacritical marks (NFD decomposition)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into words."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return text.split()


def _levenshtein(a: str, b: str) -> int:
    """Standard Levenshtein distance."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _is_accent_error(expected: str, actual: str) -> bool:
    """True if the only difference is accents/diacritics."""
    return _strip_accents(expected) == _strip_accents(actual)


def score_answer(expected: str, actual: str) -> tuple[int, list[dict]]:
    """Score a dictation answer.

    Returns (score 0-4, list of correction dicts).
    Each correction: {"expected": str, "actual": str, "type": "accent"|"typo"|"wrong"|"missing"|"extra"}
    """
    exp_words = _tokenize(expected)
    act_words = _tokenize(actual)

    if not exp_words:
        return 4, []

    corrections: list[dict] = []
    total_words = len(exp_words)

    # Align words using simple LCS-based diff
    aligned = _align(exp_words, act_words)

    accent_errors = 0
    typo_errors = 0
    wrong_errors = 0

    for kind, exp_w, act_w in aligned:
        if kind == "match":
            continue
        elif kind == "accent":
            accent_errors += 1
            corrections.append({"expected": exp_w, "actual": act_w, "type": "accent"})
        elif kind == "typo":
            typo_errors += 1
            corrections.append({"expected": exp_w, "actual": act_w, "type": "typo"})
        elif kind == "missing":
            wrong_errors += 1
            corrections.append({"expected": exp_w, "actual": "", "type": "missing"})
        elif kind == "extra":
            wrong_errors += 1
            corrections.append({"expected": "", "actual": act_w, "type": "extra"})
        else:  # wrong
            wrong_errors += 1
            corrections.append({"expected": exp_w, "actual": act_w, "type": "wrong"})

    # Calculate deductions as fraction of total words
    deduction = (
        (wrong_errors * 1.0 / total_words) * 4
        + (typo_errors * 0.5 / total_words) * 4
        + (accent_errors * 0.25 / total_words) * 4
    )

    score = max(0, round(4 - deduction))
    return score, corrections


def _align(
    expected: list[str], actual: list[str],
) -> list[tuple[str, str, str]]:
    """Align two word lists and classify each pair.

    Returns list of (kind, expected_word, actual_word).
    kind: match | accent | typo | wrong | missing | extra
    """
    m, n = len(expected), len(actual)

    # DP table for edit distance on word level
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if expected[i - 1] == actual[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    # Backtrace
    result: list[tuple[str, str, str]] = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and expected[i - 1] == actual[j - 1]:
            result.append(("match", expected[i - 1], actual[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            # Substitution — classify it
            e, a = expected[i - 1], actual[j - 1]
            if _is_accent_error(e, a):
                result.append(("accent", e, a))
            elif _levenshtein(e, a) <= 2:
                result.append(("typo", e, a))
            else:
                result.append(("wrong", e, a))
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j] == dp[i][j - 1] + 1):
            result.append(("extra", "", actual[j - 1]))
            j -= 1
        else:
            result.append(("missing", expected[i - 1], ""))
            i -= 1

    result.reverse()
    return result
