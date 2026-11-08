"""Conversation-starter category and question data."""

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CATEGORY_DESCRIPTIONS = {
    "general": "General questions",
    "phil": "Philosophical questions",
    "would": "'Would you rather' questions",
    "other": "Random questions",
    "cursed": "Cursed deals: amazing power, terrible catch",
}


@dataclass(frozen=True)
class CategoryStyle:
    """How a category looks on its topic card and hint button."""

    emoji: str
    label: str
    colour: int


CATEGORY_STYLES: dict[str, CategoryStyle] = {
    "general": CategoryStyle("💬", "General", 0x3498DB),
    "phil": CategoryStyle("🤔", "Philosophical", 0x9B59B6),
    "would": CategoryStyle("⚖️", "Would you rather", 0xE67E22),
    "other": CategoryStyle("🎲", "Random", 0x1ABC9C),
    "cursed": CategoryStyle("💀", "Cursed deals", 0xC0392B),
}

DATA_DIR = Path(__file__).resolve().parent / "convo_starter_data"
# Discord allows 4000 characters of text per Components v2 message; the rest
# covers the category line, heading markup and the hint row.
MAX_COMBINED_QUESTION_LENGTH = 3800

type Question = tuple[str, str]
type QuestionBank = Mapping[str, tuple[Question, ...]]

_CATEGORY_ALIASES = {
    str(index): category
    for index, category in enumerate(CATEGORY_DESCRIPTIONS, start=1)
}


def resolve_category(value: str) -> str:
    """Resolve a category name or numeric alias.

    Raises:
        ValueError: If *value* does not identify a registered category.
    """
    normalized = value.strip().casefold()
    category = _CATEGORY_ALIASES.get(normalized, normalized)
    if category not in CATEGORY_DESCRIPTIONS:
        raise ValueError(f"Unknown topic category: {value}")
    return category


def load_questions(data_dir: Path = DATA_DIR) -> QuestionBank:
    """Load and validate every registered category's question data."""
    return {
        category: _load_category(data_dir / f"{category}.csv")
        for category in CATEGORY_DESCRIPTIONS
    }


def _load_category(path: Path) -> tuple[Question, ...]:
    try:
        csv_file = path.open(newline="", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{path}: could not read topic data") from exc

    questions: list[Question] = []
    first_seen: dict[Question, int] = {}
    with csv_file:
        reader = csv.reader(csv_file, strict=True)
        try:
            for line_number, row in enumerate(reader, start=1):
                if len(row) != 2:
                    raise ValueError(
                        f"{path}:{line_number}: expected exactly two columns"
                    )

                question = (row[0].strip(), row[1].strip())
                if not all(question):
                    raise ValueError(
                        f"{path}:{line_number}: questions must be non-empty"
                    )
                if sum(map(len, question)) > MAX_COMBINED_QUESTION_LENGTH:
                    raise ValueError(
                        f"{path}:{line_number}: question pair exceeds "
                        f"{MAX_COMBINED_QUESTION_LENGTH} characters"
                    )
                if question in first_seen:
                    raise ValueError(
                        f"{path}:{line_number}: duplicate of line "
                        f"{first_seen[question]}"
                    )

                first_seen[question] = line_number
                questions.append(question)
        except csv.Error as exc:
            raise ValueError(
                f"{path}:{reader.line_num}: invalid CSV: {exc}"
            ) from exc

    if not questions:
        raise ValueError(f"{path}: contains no questions")
    return tuple(questions)
