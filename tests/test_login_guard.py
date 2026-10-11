"""A rejected Discord login must wait before the process exits."""
from __future__ import annotations

import logging
from collections.abc import Callable

import discord
import pytest

from cogs.utils.login_guard import RETRY_DELAY_SECONDS, run_with_login_guard


def _raiser(exc: BaseException) -> Callable[[], None]:
    def run() -> None:
        raise exc

    return run


@pytest.mark.parametrize(
    ("exc", "log_fragment"),
    [
        (discord.PrivilegedIntentsRequired(None), "privileged intents"),
        (discord.LoginFailure("Improper token has been passed."), "bot token"),
    ],
)
def test_rejected_login_waits_then_exits(
    exc: BaseException, log_fragment: str, caplog: pytest.LogCaptureFixture,
) -> None:
    waits: list[float] = []

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exit_info:
        run_with_login_guard(_raiser(exc), sleep=waits.append)

    assert exit_info.value.code == 1
    assert waits == [RETRY_DELAY_SECONDS]
    assert log_fragment in caplog.text


def test_clean_return_does_not_wait() -> None:
    waits: list[float] = []

    run_with_login_guard(lambda: None, sleep=waits.append)

    assert waits == []


def test_other_errors_propagate_without_waiting() -> None:
    waits: list[float] = []

    with pytest.raises(RuntimeError, match="boom"):
        run_with_login_guard(_raiser(RuntimeError("boom")), sleep=waits.append)

    assert waits == []
