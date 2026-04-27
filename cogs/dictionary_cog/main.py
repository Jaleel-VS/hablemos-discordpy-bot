"""Dictionary cog."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp
import discord
from beautifulsoup4 import BeautifulSoup
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, red_embed, yellow_embed

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DefinitionResult:
    """Normalized dictionary lookup result."""

    word: str
    source_key: str
    source_name: str
    definitions: list[str]
    url: str | None = None


class DictionaryCog(BaseCog):
    """Look up words in selected dictionary sources."""

    SOURCES: dict[str, str] = {
        "web": "Merriam-Webster",
        "wiktionary": "Wiktionary",
        "rae": "RAE / DLE",
        "asale": "ASALE / DLE",
        "damer": "ASALE / DAMER",
        "oxf": "Oxford",
        "oxford": "Oxford",
        "cambridge": "Cambridge",
    }

    SOURCE_ALIASES: dict[str, str] = {
        "wikt": "wiktionary",
        "wiki": "wiktionary",
        "dle": "rae",
        "americanismos": "damer",
        "dammer": "damer",
        "ox": "oxf",
        "mw": "web",
        "merriam": "web",
        "webster": "web",
    }

    MAX_DEFINITIONS = 5
    REQUEST_TIMEOUT_SECONDS = 12

    def _normalize_source(self, source: str) -> str:
        """Normalize source aliases."""
        source = source.lower().strip()
        return self.SOURCE_ALIASES.get(source, source)

    def _clean_text(self, text: str) -> str:
        """Collapse whitespace and remove common noisy fragments."""
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\[editar\]", "", text, flags=re.I)
        return text.strip()

    async def _fetch_html(self, url: str) -> str:
        """Fetch HTML from a dictionary source."""
        timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT_SECONDS)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; HablemosBot/1.0; "
                "+https://github.com/Jaleel-VS/hablemos-discordpy-bot)"
            ),
        }

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.text()

    async def _define_rae(self, word: str, source_key: str = "rae") -> DefinitionResult | None:
        """Look up a word in the DLE."""
        url = f"https://dle.rae.es/{quote(word)}"
        html = await self._fetch_html(url)
        soup = BeautifulSoup(html, "lxml")

        definitions: list[str] = []
        for item in soup.select("p.j"):
            text = self._clean_text(item.get_text(" ", strip=True))
            if text:
                definitions.append(text)

            if len(definitions) >= self.MAX_DEFINITIONS:
                break

        if not definitions:
            return None

        return DefinitionResult(
            word=word,
            source_key=source_key,
            source_name=self.SOURCES[source_key],
            definitions=definitions,
            url=url,
        )

    async def _define_damer(self, word: str) -> DefinitionResult | None:
        """Look up a word in the Diccionario de americanismos."""
        url = f"https://www.asale.org/damer/{quote(word)}"
        html = await self._fetch_html(url)
        soup = BeautifulSoup(html, "lxml")

        definitions: list[str] = []

        for item in soup.select("article p, .field-name-body p, .entry-content p, p"):
            text = self._clean_text(item.get_text(" ", strip=True))
            lowered = text.lower()

            if not text or len(text) < 12:
                continue
            if "diccionario de americanismos" in lowered:
                continue
            if "asociación de academias" in lowered:
                continue
            if "buscador general" in lowered:
                continue

            definitions.append(text)

            if len(definitions) >= self.MAX_DEFINITIONS:
                break

        if not definitions:
            return None

        return DefinitionResult(
            word=word,
            source_key="damer",
            source_name=self.SOURCES["damer"],
            definitions=definitions,
            url=url,
        )

    async def _define_wiktionary(self, word: str, source_key: str = "wiktionary") -> DefinitionResult | None:
        """Look up a word in Wiktionary."""
        url = f"https://en.wiktionary.org/wiki/{quote(word)}"
        html = await self._fetch_html(url)
        soup = BeautifulSoup(html, "lxml")

        content = soup.select_one("#mw-content-text")
        if content is None:
            return None

        definitions: list[str] = []
        for item in content.select("ol > li"):
            text = self._clean_text(item.get_text(" ", strip=True))
            text = re.sub(r"\[quotations ▼\].*$", "", text).strip()
            text = re.sub(r"\(.*?please add.*?\)", "", text, flags=re.I).strip()

            if len(text) < 8:
                continue

            definitions.append(text)

            if len(definitions) >= self.MAX_DEFINITIONS:
                break

        if not definitions:
            return None

        return DefinitionResult(
            word=word,
            source_key=source_key,
            source_name=self.SOURCES[source_key],
            definitions=definitions,
            url=url,
        )

    async def _define_not_configured(self, word: str, source_key: str) -> DefinitionResult:
        """Return a controlled response for sources that need API/legal setup."""
        return DefinitionResult(
            word=word,
            source_key=source_key,
            source_name=self.SOURCES[source_key],
            definitions=[
                "This dictionary source is registered, but not configured yet.",
                "Use `rae`, `asale`, `damer`, `wiktionary`, or `web` for now.",
            ],
            url=None,
        )

    async def _lookup(self, source_key: str, word: str) -> DefinitionResult | None:
        """Dispatch lookup to the selected source."""
        if source_key == "rae":
            return await self._define_rae(word, "rae")

        if source_key == "asale":
            return await self._define_rae(word, "asale")

        if source_key == "damer":
            return await self._define_damer(word)

        if source_key == "web":
            return await self._define_not_configured(word, "web")

        if source_key == "wiktionary":
            return await self._define_wiktionary(word, "wiktionary")

        if source_key in {"oxf", "oxford", "cambridge"}:
            normalized = "oxf" if source_key in {"oxf", "oxford"} else "cambridge"
            return await self._define_not_configured(word, normalized)

        return None

    def _build_result_embed(self, result: DefinitionResult) -> discord.Embed:
        """Build a Hablemos-style result embed."""
        lines = []
        for index, definition in enumerate(result.definitions[: self.MAX_DEFINITIONS], start=1):
            if len(definition) > 500:
                definition = definition[:497] + "..."
            lines.append(f"**{index}.** {definition}")

        embed = discord.Embed(
            title=f"📖 {result.word}",
            description="\n\n".join(lines),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="Source",
            value=result.source_name,
            inline=True,
        )

        if result.url:
            embed.add_field(
                name="Entry",
                value=f"[Open dictionary entry]({result.url})",
                inline=True,
            )

        embed.set_footer(text=f"{len(result.definitions[: self.MAX_DEFINITIONS])} definition(s)")
        return embed

    def _build_sources_embed(self) -> discord.Embed:
        """Build source list embed."""
        lines = [
            "`web` / `webster` — Merriam-Webster. Registered, not configured",
            "`wiktionary` — open multilingual dictionary",
            "`rae` / `dle` — Diccionario de la lengua española",
            "`asale` — academic Spanish lookup through DLE",
            "`damer` — Diccionario de americanismos",
            "`oxf` / `oxford` — registered, not configured",
            "`cambridge` — registered, not configured",
        ]

        embed = discord.Embed(
            title="📚 Dictionary Sources",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Usage: $define <source> <word>")
        return embed

    @commands.command(name="define", aliases=["def", "meaning"])
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def define_command(
        self,
        ctx: commands.Context,
        source: str | None = None,
        *,
        word: str | None = None,
    ) -> None:
        """Look up a word in a selected dictionary source."""
        if source is None:
            await ctx.send(embed=self._build_sources_embed())
            return

        if source.lower() in {"sources", "source", "dicts", "dictionaries"}:
            await ctx.send(embed=self._build_sources_embed())
            return

        if word is None:
            await ctx.send(
                embed=yellow_embed(
                    f"Usage: `{ctx.prefix}define <source> <word>`\n"
                    f"Example: `{ctx.prefix}define rae casa`",
                ),
            )
            return

        source_key = self._normalize_source(source)
        if source_key not in self.SOURCES:
            await ctx.send(
                embed=red_embed(
                    f"Unknown source `{source}`.\n"
                    f"Use `{ctx.prefix}define sources` to see available sources.",
                ),
            )
            return

        async with ctx.typing():
            try:
                result = await self._lookup(source_key, word.strip())
            except aiohttp.ClientResponseError as exc:
                logger.warning("Dictionary HTTP error for %s/%s: %s", source_key, word, exc)
                await ctx.send(
                    embed=red_embed("The dictionary source rejected or failed the request."),
                )
                return
            except aiohttp.ClientError as exc:
                logger.warning("Dictionary network error for %s/%s: %s", source_key, word, exc)
                await ctx.send(embed=red_embed("Could not reach the dictionary source."))
                return
            except Exception:
                logger.exception("Unexpected dictionary error for %s/%s", source_key, word)
                await ctx.send(embed=red_embed("Unexpected dictionary error."))
                return

        if result is None:
            await ctx.send(
                embed=yellow_embed(
                    f"No definition found for `{word}` in `{source_key}`.\n"
                    f"Try `{ctx.prefix}define web {word}` or `{ctx.prefix}define rae {word}`.",
                ),
            )
            return

        await ctx.send(embed=self._build_result_embed(result))


async def setup(bot) -> None:
    await bot.add_cog(DictionaryCog(bot))
