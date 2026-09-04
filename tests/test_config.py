"""Tests for centralized environment configuration helpers."""

import pytest

from config import get_int_list_env


def test_get_int_list_env_uses_integer_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_IDS", raising=False)

    assert get_int_list_env("TEST_IDS", [1, 2]) == [1, 2]


def test_get_int_list_env_parses_comma_delimited_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_IDS", " 3, 4 ,, 5 ")

    assert get_int_list_env("TEST_IDS", [1, 2]) == [3, 4, 5]


def test_get_int_list_env_names_invalid_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_IDS", "3,nope")

    with pytest.raises(
        ValueError,
        match="TEST_IDS must be a comma-delimited list of integers",
    ):
        get_int_list_env("TEST_IDS", [1, 2])
