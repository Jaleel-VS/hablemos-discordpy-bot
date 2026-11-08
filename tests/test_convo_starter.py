"""Command tests for the conversation-starter cog."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, TypedDict, cast

import discord

from cogs.convo_starter_cog.main import HINT_CHOICES, HINT_GAPS, ConvoStarter
from cogs.convo_starter_cog.questions import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_STYLES,
)
from cogs.convo_starter_cog.views import TopicCard


@dataclass
class FakeChannel:
    """Minimal Discord channel with an ID."""

    id: int


class SendKwargs(TypedDict, total=False):
    """Keyword arguments captured from a fake context send."""

    embed: discord.Embed
    view: discord.ui.LayoutView


@dataclass
class FakeContext:
    """Minimal command context that records sent messages."""

    channel_id: int
    clean_prefix: str = "$"
    channel: FakeChannel = field(init=False)
    sent: list[tuple[tuple[Any, ...], SendKwargs]] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self.channel = FakeChannel(self.channel_id)

    async def send(self, *args: Any, **kwargs: Any) -> object:
        captured: SendKwargs = {}
        if "embed" in kwargs:
            captured["embed"] = kwargs["embed"]
        if "view" in kwargs:
            captured["view"] = kwargs["view"]
        self.sent.append((args, captured))
        return object()


def _question_text(view: discord.ui.LayoutView) -> str:
    """The card's first text block: category line, question, translation."""
    first = next(c for c in view.walk_children() if isinstance(c, discord.ui.TextDisplay))
    return first.content


def _hint_labels(view: discord.ui.LayoutView) -> list[str | None]:
    return [c.label for c in view.walk_children() if isinstance(c, discord.ui.Button)]


def _make_cog(spanish_first_channels: list[int] | None = None) -> ConvoStarter:
    bot = SimpleNamespace(
        settings=SimpleNamespace(
            convo_spa_channels=spanish_first_channels or []
        )
    )
    return ConvoStarter(cast(Any, bot))


async def _run_topic(
    cog: ConvoStarter,
    ctx: FakeContext,
    category: str | None = None,
) -> None:
    callback = cast(Any, cog.topic.callback)
    if category is None:
        await callback(cog, ctx)
    else:
        await callback(cog, ctx, category=category)


async def _run_list(cog: ConvoStarter, ctx: FakeContext) -> None:
    callback = cast(Any, cog.lst.callback)
    await callback(cog, ctx)


async def test_topic_defaults_to_general(monkeypatch: Any) -> None:
    cog = _make_cog()
    cog.questions["general"] = (("Pregunta", "Question"),)
    ctx = FakeContext(channel_id=1)
    monkeypatch.setattr(
        "cogs.convo_starter_cog.main.choice", lambda options: options[0]
    )

    await _run_topic(cog, ctx)

    view = ctx.sent[0][1]["view"]
    assert _question_text(view) == "-# 💬 General questions\n### Question\nPregunta"


async def test_topic_accepts_case_insensitive_numeric_alias(
    monkeypatch: Any,
) -> None:
    cog = _make_cog()
    cog.questions["cursed"] = (("Trato", "Deal"),)
    ctx = FakeContext(channel_id=1)
    monkeypatch.setattr(
        "cogs.convo_starter_cog.main.choice", lambda questions: questions[0]
    )

    await _run_topic(cog, ctx, " 5 ")

    view = ctx.sent[0][1]["view"]
    assert _question_text(view).endswith("### Deal\nTrato")


async def test_topic_places_spanish_first_in_configured_channel(
    monkeypatch: Any,
) -> None:
    cog = _make_cog(spanish_first_channels=[42])
    cog.questions["phil"] = (("Español", "English"),)
    ctx = FakeContext(channel_id=42)
    monkeypatch.setattr(
        "cogs.convo_starter_cog.main.choice", lambda questions: questions[0]
    )

    await _run_topic(cog, ctx, "PHIL")

    view = ctx.sent[0][1]["view"]
    assert _question_text(view).endswith("### Español\nEnglish")


async def test_invalid_topic_uses_prefix_and_resets_cooldown(
    monkeypatch: Any,
) -> None:
    cog = _make_cog()
    ctx = FakeContext(channel_id=1, clean_prefix="!")
    reset_contexts: list[FakeContext] = []
    monkeypatch.setattr(
        cog.topic,
        "reset_cooldown",
        lambda reset_ctx: reset_contexts.append(reset_ctx),
    )

    await _run_topic(cog, ctx, "not real")

    assert reset_contexts == [ctx]
    assert ctx.sent == [
        (
            ("Topic not found. Type `!lst` to see the available categories.",),
            {},
        )
    ]


async def test_list_is_generated_from_categories_and_prefix() -> None:
    cog = _make_cog()
    ctx = FakeContext(channel_id=1, clean_prefix="!")

    await _run_list(cog, ctx)

    embed = ctx.sent[0][1].get("embed")
    assert embed is not None
    description = embed.description or ""
    assert "`!topic <category>`" in description
    for index, category in enumerate(CATEGORY_DESCRIPTIONS, start=1):
        assert f"`{category}`, `{index}`" in description


def test_every_category_has_a_style() -> None:
    assert CATEGORY_STYLES.keys() == CATEGORY_DESCRIPTIONS.keys()


def test_hints_land_every_two_to_four_topics_per_channel() -> None:
    random.seed(7)
    cog = _make_cog()
    hint_turns = [n for n in range(1, 301) if cog._deal(1, "general").buttons]
    gaps = {b - a for a, b in zip([0, *hint_turns], hint_turns, strict=False)}
    assert gaps == set(HINT_GAPS)
    # Another channel's pacing is untouched by channel 1's topics.
    assert not cog._deal(2, "general").buttons


def test_hint_offers_other_distinct_categories() -> None:
    random.seed(3)
    cog = _make_cog()
    for _ in range(200):
        card = cog._deal(1, "phil")
        if not card.buttons:
            continue
        labels = _hint_labels(card)
        assert len(set(labels)) == HINT_CHOICES
        assert CATEGORY_STYLES["phil"].label not in labels


def test_longest_question_with_hint_fits_message_limit() -> None:
    cog = _make_cog()
    longest = max(
        (pair for pairs in cog.questions.values() for pair in pairs),
        key=lambda pair: len(pair[0]) + len(pair[1]),
    )
    card = TopicCard(
        "would", *longest, hints=["general", "phil", "cursed"], on_pick=cast(Any, None)
    )
    assert card.content_length() <= 4000


@dataclass
class FakeResponse:
    """Records interaction responses."""

    sent: list[dict[str, Any]] = field(default_factory=list)

    async def send_message(self, content: str | None = None, **kwargs: Any) -> None:
        self.sent.append({"content": content, **kwargs})


def _interaction(user_id: int) -> Any:
    # Shaped like discord.Interaction: .user, no .author.
    async def original_response() -> object:
        return object()

    return SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        channel_id=1,
        response=FakeResponse(),
        original_response=original_response,
    )


async def test_hint_click_posts_topic_then_rate_limits_that_user() -> None:
    cog = _make_cog()
    first, again, other = _interaction(5), _interaction(5), _interaction(6)

    await cog._pick(first, "cursed")
    await cog._pick(again, "cursed")
    await cog._pick(other, "cursed")

    assert isinstance(first.response.sent[0]["view"], TopicCard)
    assert again.response.sent[0]["ephemeral"] is True
    assert "view" not in again.response.sent[0]
    assert isinstance(other.response.sent[0]["view"], TopicCard)
