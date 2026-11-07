"""Souls cog — random quotes from Dark Souls III, Bloodborne and Sekiro."""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import AllowedMentions, ui
from discord.ext import commands

from base_cog import BaseCog

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

_DATA = Path(__file__).parent / "data" / "quotes.json"


@dataclass(frozen=True)
class Game:
    """A game whose quotes can be drawn."""

    title: str
    accent: discord.Colour


GAMES: dict[str, Game] = {
    "ds3": Game("Dark Souls III", discord.Colour.from_str("#c0662b")),
    "bb": Game("Bloodborne", discord.Colour.from_str("#8b1e1e")),
    "sekiro": Game("Sekiro: Shadows Die Twice", discord.Colour.from_str("#d4a017")),
}

# User-typed game names → GAMES key.
_ALIASES: dict[str, str] = {
    "ds3": "ds3", "ds": "ds3", "darksouls": "ds3", "darksouls3": "ds3",
    "bb": "bb", "bloodborne": "bb",
    "sekiro": "sekiro", "sdt": "sekiro",
}


@dataclass(frozen=True)
class Quote:
    """One line of dialogue, who says it, and the wiki page it was checked against."""

    game: str
    speaker: str
    text: str
    source_url: str


def load_quotes(path: Path = _DATA) -> list[Quote]:
    """Load every quote, rejecting unknown games, empty games and blank fields."""
    raw: dict[str, list[dict[str, str]]] = json.loads(path.read_text(encoding="utf-8"))
    if raw.keys() != GAMES.keys():
        raise ValueError(f"quotes.json games {sorted(raw)} != {sorted(GAMES)}")
    quotes: list[Quote] = []
    for game, entries in raw.items():
        if not entries:
            raise ValueError(f"quotes.json has no quotes for {game}")
        for entry in entries:
            quote = Quote(game, entry["speaker"].strip(), entry["text"].strip(), entry["source_url"])
            if not (quote.speaker and quote.text and quote.source_url.startswith("https://")):
                raise ValueError(f"quotes.json has an incomplete {game} entry: {entry}")
            quotes.append(quote)
    return quotes


def format_quote(text: str) -> str:
    """Markdown for a quote; each dialogue line is its own italic heading.

    Headings and ``*italics*`` stop at a newline, so multi-line dialogue is
    formatted line by line, with the quote marks opening and closing the whole.
    """
    lines = text.split("\n")
    lines[0] = f"“{lines[0]}"
    lines[-1] = f"{lines[-1]}”"
    return "\n".join(f"### *{line}*" for line in lines)


def build_quote_view(quote: Quote) -> ui.LayoutView:
    """Components V2 card for a single quote."""
    game = GAMES[quote.game]
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(
        ui.TextDisplay(format_quote(quote.text)),
        ui.Separator(visible=True),
        ui.TextDisplay(f"-# — {quote.speaker} · {game.title}"),
        accent_colour=game.accent,
    ))
    return view


class SoulsCog(BaseCog):
    """Random FromSoftware quotes."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)
        self.quotes = load_quotes()

    @commands.command(
        name="souls", aliases=["fromsoft"],
        help="Random Dark Souls III, Bloodborne or Sekiro quote. Usage: $souls [ds3|bb|sekiro]",
    )
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def souls(self, ctx: commands.Context, game: str | None = None) -> None:
        """Send a random quote, optionally from one game."""
        pool = self.quotes
        if game is not None:
            key = _ALIASES.get(game.lower())
            if key is None:
                await ctx.send(
                    "Unknown game. Try `$souls`, `$souls ds3`, `$souls bb` or `$souls sekiro`.",
                    allowed_mentions=AllowedMentions.none(),
                )
                return
            pool = [q for q in self.quotes if q.game == key]
        await ctx.send(view=build_quote_view(random.choice(pool)))


async def setup(bot: Hablemos) -> None:
    """Register the SoulsCog with the bot."""
    await bot.add_cog(SoulsCog(bot))
    logger.info("SoulsCog registered")
