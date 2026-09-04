"""Tests for conversation-starter category resolution and CSV loading."""

from pathlib import Path

import pytest

from cogs.convo_starter_cog.questions import (
    CATEGORY_DESCRIPTIONS,
    DATA_DIR,
    MAX_COMBINED_QUESTION_LENGTH,
    load_questions,
    resolve_category,
)


def _write_category_files(
    data_dir: Path, general: str = "Hola,Hello\n"
) -> None:
    data_dir.mkdir(exist_ok=True)
    for category in CATEGORY_DESCRIPTIONS:
        content = general if category == "general" else "Pregunta,Question\n"
        (data_dir / f"{category}.csv").write_text(content, encoding="utf-8")


def test_shipped_question_bank_matches_registered_categories() -> None:
    question_bank = load_questions()

    assert set(question_bank) == set(CATEGORY_DESCRIPTIONS)
    assert {path.stem for path in DATA_DIR.glob("*.csv")} == set(
        CATEGORY_DESCRIPTIONS
    )
    assert all(question_bank.values())
    assert all(
        0 < sum(map(len, question)) <= MAX_COMBINED_QUESTION_LENGTH
        for questions in question_bank.values()
        for question in questions
    )


def test_legacy_helper_exports_remain_compatible() -> None:
    from cogs.convo_starter_cog.convo_starter_help import (
        categories,
        get_random_question,
    )

    assert categories == list(CATEGORY_DESCRIPTIONS)
    assert get_random_question("1") in load_questions()["general"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("general", "general"),
        (" General ", "general"),
        ("PHIL", "phil"),
        ("1", "general"),
        ("5", "cursed"),
    ],
)
def test_resolve_category_accepts_names_and_numeric_aliases(
    value: str,
    expected: str,
) -> None:
    assert resolve_category(value) == expected


@pytest.mark.parametrize("value", ["", "0", "6", "unknown", "phil extra"])
def test_resolve_category_rejects_unknown_values(value: str) -> None:
    with pytest.raises(ValueError, match="Unknown topic category"):
        resolve_category(value)


def test_load_questions_reports_missing_file(tmp_path: Path) -> None:
    _write_category_files(tmp_path)
    (tmp_path / "general.csv").unlink()

    with pytest.raises(ValueError, match=r"general\.csv: could not read"):
        load_questions(tmp_path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "contains no questions"),
        ("Spanish only\n", "expected exactly two columns"),
        (",English\n", "questions must be non-empty"),
        ("Spanish,\n", "questions must be non-empty"),
        ("Spanish,English\nSpanish,English\n", "duplicate of line 1"),
        ('"unterminated,English\n', "invalid CSV"),
        (
            f"{'x' * (MAX_COMBINED_QUESTION_LENGTH + 1)},English\n",
            f"question pair exceeds {MAX_COMBINED_QUESTION_LENGTH} characters",
        ),
    ],
)
def test_load_questions_rejects_invalid_data(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    _write_category_files(tmp_path, general=content)

    with pytest.raises(ValueError, match=message) as exc_info:
        load_questions(tmp_path)

    assert "general.csv" in str(exc_info.value)
