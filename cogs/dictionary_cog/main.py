"""Dictionary cog."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp
import discord
from bs4 import BeautifulSoup
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
        "damer": "ASALE / DAMER",
        "oxf": "Oxford",
        "oxford": "Oxford",
        "cambridge": "Cambridge",
    }

    SOURCE_ALIASES: dict[str, str] = {
        "wikt": "wiktionary",
        "wiki": "wiktionary",
        "americanismos": "damer",
        "dammer": "damer",
        "ox": "oxf",
        "mw": "web",
        "merriam": "web",
        "webster": "web",
    }

    MAX_DEFINITIONS = 3 #Adjust this to set the maximum definitions in the answer.
    REQUEST_TIMEOUT_SECONDS = 12 #How much have the server to answer the request.
    MAX_DEFINITION_WORDS = 200 #How much words can Hablemos-Bot answer.

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

    async def _define_wiktionary(
        self,
        word: str,
        source_key: str = "wiktionary",
        lang: str | None = None,
    ) -> DefinitionResult | None:
        """Look up a word in Wiktionary, optionally using a language-specific Wiktionary."""
        lang = (lang or "en").lower().strip()

        wiki_domains = {
            "en": "en.wiktionary.org",
            "es": "es.wiktionary.org",
            "jp": "ja.wiktionary.org",
            "ja": "ja.wiktionary.org",
            "ko": "ko.wiktionary.org",
            "fr": "fr.wiktionary.org",
            "de": "de.wiktionary.org",
            "it": "it.wiktionary.org",
            "pt": "pt.wiktionary.org",
            "zh": "zh.wiktionary.org",
            "ru": "ru.wiktionary.org",
        }

        domain = wiki_domains.get(lang, "en.wiktionary.org")
        url = f"https://{domain}/wiki/{quote(word)}"

        html = await self._fetch_html(url)
        soup = BeautifulSoup(html, "lxml")

        definitions: list[str] = []

        # Spanish Wiktionary uses definition lists more reliably than ordered lists.
        if lang == "es":
            content = soup.select_one("#mw-content-text")
            if content is None:
                return None

            for item in content.select("dd"):
                text = self._clean_text(item.get_text(" ", strip=True))

                if not text:
                    continue
                if len(text) < 8:
                    continue
                if text.lower().startswith(("del latín", "plural", "pronunciación")):
                    continue
                if "editar" in text.lower():
                    continue

                definitions.append(text)

                if len(definitions) >= self.MAX_DEFINITIONS:
                    break

        else:
            content = soup.select_one("#mw-content-text")
            if content is None:
                return None

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

        source_name = self.SOURCES[source_key]
        if lang:
            source_name = f"{source_name} / {lang}"

        return DefinitionResult(
            word=word,
            source_key=source_key,
            source_name=source_name,
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
                "Use `wiktionary` or `damer` for now.",
            ],
            url=None,
        )

    async def _lookup(
        self,
        source_key: str,
        word: str,
        lang: str | None = None,
    ) -> DefinitionResult | None:
        """Dispatch lookup to the selected source."""
        if source_key in {"web", "oxf", "oxford", "cambridge"}:
            normalized = "oxf" if source_key in {"oxf", "oxford"} else source_key
            return await self._define_not_configured(word, normalized)

        if source_key == "damer":
            return await self._define_damer(word)

        if source_key == "wiktionary":
            return await self._define_wiktionary(word, "wiktionary", lang=lang)

        return None

    def _shorten_definition(self, text: str) -> tuple[str, bool]:
        """Shorten a definition if it exceeds the word limit."""
        words = text.split()

        if len(words) <= self.MAX_DEFINITION_WORDS:
            return text, False

        shortened = " ".join(words[: self.MAX_DEFINITION_WORDS])
        return (
            f"{shortened}...\n\n*Para más significados, ve a la página fuente.*",
            True,
        )
    def _build_result_embed(self, result: DefinitionResult) -> discord.Embed:
        """Build a Hablemos-style result embed."""
        lines = []
        was_shortened = False

        for index, definition in enumerate(result.definitions[: self.MAX_DEFINITIONS], start=1):
            definition, shortened = self._shorten_definition(definition)
            was_shortened = was_shortened or shortened

            if len(definition) > 900:
                definition = definition[:897] + "..."

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

        footer = f"{len(result.definitions[: self.MAX_DEFINITIONS])} definition(s)"
        if was_shortened:
            footer += " • Shortened"

        embed.set_footer(text=footer)
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
        first: str | None = None,
        second: str | None = None,
        *,
        rest: str | None = None,
    ) -> None:
        """Look up a word in a selected dictionary source."""
        if first is None:
            await ctx.send(embed=self._build_sources_embed())
            return

        if first.lower() in {"sources", "source", "dicts", "dictionaries"}:
            await ctx.send(embed=self._build_sources_embed())
            return

        source_key: str
        word: str
        lang: str | None = None

        normalized_first = self._normalize_source(first)

        valid_langs = {"en", "es", "jp", "ja", "ko", "fr", "de", "it", "pt", "zh", "ru"}

        if (
            normalized_first in valid_langs
            and second is not None
            and rest is None
        ):
            await ctx.send(
                embed=yellow_embed(
                    f"Malformed command. Use `{ctx.prefix}define wiki <lang> <word>`."
                ),
            )
            return
        if normalized_first not in self.SOURCES:
            source_key = "wiktionary"
            word = " ".join(part for part in [first, second, rest] if part)

        elif normalized_first == "wiktionary" and second is not None and rest is not None:
            source_key = "wiktionary"
            lang = second.lower().strip()
            word = rest.strip()

        else:
            source_key = normalized_first
            word = " ".join(part for part in [second, rest] if part)

        if not word:
            await ctx.send(
                embed=yellow_embed(
                    f"Usage: `{ctx.prefix}define <word>`\n"
                    f"Or: `{ctx.prefix}define <source> <word>`\n"
                    f"Or: `{ctx.prefix}define wiki <lang> <word>`",
                ),
            )
            return

        async with ctx.typing():
            try:
                result = await self._lookup(source_key, word.strip(), lang=lang)
            except aiohttp.ClientResponseError as exc:
                logger.warning("Dictionary HTTP error for %s/%s: %s", source_key, word, exc)
                await ctx.send(embed=red_embed("The dictionary source rejected or failed the request."))
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
            lang_text = f" with language `{lang}`" if lang else ""
            await ctx.send(
                embed=yellow_embed(
                    f"No definition found for `{word}` in `{source_key}`{lang_text}.",
                ),
            )
            return

        await ctx.send(embed=self._build_result_embed(result))

"""Setup"""
async def setup(bot) -> None:
    await bot.add_cog(DictionaryCog(bot))
