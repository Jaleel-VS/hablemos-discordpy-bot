"""Inclusive summarize ranges must not duplicate boundary messages."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from cogs.summary_cog.message_parser import collect_range_messages


@dataclass(frozen=True)
class FakeAuthor:
    bot: bool
    display_name: str


@dataclass(frozen=True)
class FakeMessage:
    id: int
    author: FakeAuthor
    content: str
    created_at: datetime


def _msg(
    mid: int,
    content: str,
    *,
    bot: bool = False,
    minute: int = 0,
) -> FakeMessage:
    return FakeMessage(
        id=mid,
        author=FakeAuthor(bot=bot, display_name="Ada"),
        content=content,
        created_at=datetime(2026, 10, 3, 12, minute, tzinfo=UTC),
    )


def test_same_start_and_end_is_one_message() -> None:
    msg = _msg(10, "hola")
    collected = collect_range_messages([], msg, msg)
    assert [row["content"] for row in collected] == ["hola"]


def test_history_plus_boundaries_does_not_duplicate() -> None:
    start = _msg(1, "start", minute=1)
    mid = _msg(2, "mid", minute=2)
    end = _msg(3, "end", minute=3)
    # Simulate an API that already included the end message.
    collected = collect_range_messages([mid, end], start, end)
    assert [row["content"] for row in collected] == ["start", "mid", "end"]


def test_bots_and_blank_content_are_skipped() -> None:
    start = _msg(1, "  ", minute=1)
    bot_msg = _msg(2, "beep", bot=True, minute=2)
    end = _msg(3, "end", minute=3)
    collected = collect_range_messages([bot_msg], start, end)
    assert [row["content"] for row in collected] == ["end"]


def test_optional_links_use_message_id() -> None:
    start = _msg(8, "a", minute=1)
    end = _msg(9, "b", minute=2)
    collected = collect_range_messages(
        [], start, end, include_link=True, guild_id=1, channel_id=2,
    )
    assert collected[0]["link"] == "https://discord.com/channels/1/2/8"
    assert collected[1]["link"] == "https://discord.com/channels/1/2/9"
