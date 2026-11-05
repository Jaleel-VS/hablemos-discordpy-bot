"""Caller-owned minimum lengths apply after message cleaning."""
import pytest

from cogs.utils.language import detect_message_language


@pytest.mark.parametrize(
    ("content", "minimum", "expected"),
    [
        ("Thank you", 5, "en"),
        ("Thank you", 10, None),
        ("Thank you <:smile:123456>", 10, None),
        ("Thank you 😀", 10, None),
    ],
)
def test_message_length_policy(content: str, minimum: int, expected: str | None) -> None:
    assert detect_message_language(content, min_length=minimum) == expected
