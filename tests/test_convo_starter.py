"""Command tests for the conversation-starter cog."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import discord

from cogs.convo_starter_cog.main import ConvoStarter
from cogs.convo_starter_cog.questions import CATEGORY_DESCRIPTIONS


@dataclass
class FakeChannel:
    """Minimal Discord channel with an ID."""

    id: int


@dataclass
class FakeContext:
    """Minimal command context that records sent messages."""

    channel_id: int
    clean_prefix: str = "$"
    channel: FakeChannel = field(init=False)
    sent: list[tuple[tuple[Any, ...], dict[str, Any]]] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self.channel = FakeChannel(self.channel_id)

    async def send(self, *args: Any, **kwargs: Any) -> None:
        self.sent.append((args, kwargs))


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
    selected: list[tuple[tuple[str, str], ...]] = []

    def choose(options: Any) -> Any:
        if options is cog.questions["general"]:
            selected.append(options)
        return options[0]

    monkeypatch.setattr("cogs.convo_starter_cog.main.choice", choose)

    await _run_topic(cog, ctx)

    assert selected == [cog.questions["general"]]


def test_legacy_embed_helper_remains_compatible() -> None:
    from cogs.convo_starter_cog.main import embed_question

    embed = embed_question("Primary", "Translation")

    assert embed.description == "**Primary**\n\nTranslation"


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

    embed = ctx.sent[0][1]["embed"]
    assert embed.title is None
    assert embed.description == "**Deal**\n\nTrato"


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

    embed = ctx.sent[0][1]["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.title is None
    assert embed.description == "**Español**\n\nEnglish"


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

    embed = ctx.sent[0][1]["embed"]
    description = embed.description or ""
    assert "`!topic <category>`" in description
    for index, category in enumerate(CATEGORY_DESCRIPTIONS, start=1):
        assert f"`{category}`, `{index}`" in description
