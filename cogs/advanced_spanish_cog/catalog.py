"""Validated, original advanced-Spanish study cards bundled with the bot."""

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
REGISTERS = frozenset({"neutro", "coloquial", "formal", "literario"})
_FIELD_LIMITS = {
    "id": 80,
    "term": 60,
    "meaning_es": 220,
    "meaning_en": 220,
    "register": 20,
    "region": 50,
    "collocation": 100,
    "note": 180,
}


@dataclass(frozen=True, slots=True)
class Example:
    """An original Spanish usage example and its English translation."""

    es: str
    en: str


@dataclass(frozen=True, slots=True)
class VocabularyEntry:
    """One sense of an advanced word or expression, with usage guidance."""

    id: str
    term: str
    meaning_es: str
    meaning_en: str
    register: str
    region: str
    collocation: str
    note: str
    examples: tuple[Example, ...]


def normalize(text: str) -> str:
    """Normalize accents, case, and spacing for forgiving term searches."""
    return " ".join(
        "".join(
            char for char in unicodedata.normalize("NFD", text.casefold())
            if not unicodedata.combining(char)
        ).split()
    )


def _text(value: object, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Invalid vocabulary field: {label}")
    return value.strip()


def load_catalog(directory: Path = DATA_DIR) -> tuple[VocabularyEntry, ...]:
    """Load every data slice, rejecting duplicate terms and malformed cards."""
    entries: list[VocabularyEntry] = []
    ids: set[str] = set()
    terms: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"Vocabulary data must be an array: {path.name}")
        for row in rows:
            if not isinstance(row, dict) or set(row) != {*_FIELD_LIMITS, "examples"}:
                raise ValueError(f"Unexpected vocabulary fields in {path.name}")
            fields = {key: _text(row[key], limit, key) for key, limit in _FIELD_LIMITS.items()}
            if fields["register"] not in REGISTERS:
                raise ValueError(f"Unknown vocabulary register: {fields['register']}")
            raw_examples = row["examples"]
            if not isinstance(raw_examples, list) or len(raw_examples) != 2:
                raise ValueError(f"Expected two examples for {fields['term']}")
            examples: list[Example] = []
            for example in raw_examples:
                if not isinstance(example, dict) or set(example) != {"es", "en"}:
                    raise ValueError(f"Invalid example for {fields['term']}")
                examples.append(Example(
                    es=_text(example["es"], 220, "example.es"),
                    en=_text(example["en"], 220, "example.en"),
                ))
            term_key = normalize(fields["term"])
            if fields["id"] in ids or term_key in terms:
                raise ValueError(f"Duplicate vocabulary entry: {fields['term']}")
            ids.add(fields["id"])
            terms.add(term_key)
            entries.append(VocabularyEntry(**fields, examples=tuple(examples)))
    if not entries:
        raise ValueError("The advanced Spanish catalog is empty")
    return tuple(sorted(entries, key=lambda entry: normalize(entry.term)))


def find_entries(entries: tuple[VocabularyEntry, ...], query: str) -> tuple[VocabularyEntry, ...]:
    """Find an exact term first, otherwise match a fragment of its headword."""
    key = normalize(query)
    if not key:
        return entries
    matches: list[VocabularyEntry] = []
    for entry in entries:
        term = normalize(entry.term)
        if term == key:
            return (entry,)
        if key in term:
            matches.append(entry)
    return tuple(matches)
