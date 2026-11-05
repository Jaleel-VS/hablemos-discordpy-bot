"""Breakdown cog — grammatical sentence analysis via Gemini.

Users submit a sentence in Spanish or English with ``$breakdown``, and the
bot responds with a clause-level + word-level grammatical breakdown in the
*other* language (mirror approach).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from pydantic import ValidationError

from base_cog import BaseCog
from cogs.utils.embeds import red_embed, yellow_embed
from cogs.utils.gemini import GeminiError
from cogs.utils.language import detect_message_language

from .config import (
    ALLOWED_CHANNEL_IDS,
    COOLDOWN_SECONDS,
    MAX_INPUT_LENGTH,
    MIN_INPUT_LENGTH,
)
from .prompts import BREAKDOWN_PROMPT, BreakdownInput, SentenceBreakdown

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


def render_breakdown(data: SentenceBreakdown, detected_lang: str, *, detailed: bool = False) -> str:
    """Render a SentenceBreakdown into compact markdown for an embed description.

    Args:
        detailed: If True, include grammatical roles and verb/noun notes.
    """
    lines: list[str] = []

    if data.correction:
        lines.append(f"✏️ **Corrected:** {data.correction}\n")

    for clause in data.clauses:
        lines.append(f"**{clause.clause_type}:** *{clause.clause_text}*\n")
        for w in clause.words:
            if detailed:
                parts = f"`{w.word}` → **{w.translation}** — {w.part_of_speech}, {w.grammatical_role}"
                if w.notes:
                    parts += f" · *{w.notes}*"
            else:
                parts = f"`{w.word}` → **{w.translation}** — {w.part_of_speech}"
            lines.append(parts)
        lines.append("")

    lang_arrow = "🇪🇸→🇺🇸" if detected_lang == "es" else "🇺🇸→🇪🇸"
    lines.append(f"**{lang_arrow}** {data.full_translation}")

    return "\n".join(lines)


class BreakdownCog(BaseCog):
    """Sentence breakdown — grammatical analysis powered by Gemini."""

    @commands.command(name="breakdown", aliases=["bd"])
    @commands.cooldown(1, COOLDOWN_SECONDS, commands.BucketType.user)
    async def breakdown(self, ctx: commands.Context, *, sentence: str | None = None):
        """Break down a sentence (simple view).

        Usage:
            $bd <sentence in Spanish or English>
            Reply to a message with $bd
        """
        await self._do_breakdown(ctx, sentence, detailed=False)

    @commands.command(name="breakdown2", aliases=["bd2"])
    @commands.cooldown(1, COOLDOWN_SECONDS, commands.BucketType.user)
    async def breakdown2(self, ctx: commands.Context, *, sentence: str | None = None):
        """Break down a sentence (detailed view with grammar notes).

        Usage:
            $bd2 <sentence in Spanish or English>
            Reply to a message with $bd2
        """
        await self._do_breakdown(ctx, sentence, detailed=True)

    async def _do_breakdown(
        self, ctx: commands.Context, sentence: str | None, *, detailed: bool
    ) -> None:
        """Shared breakdown logic for simple and detailed commands."""
        if ctx.channel.id not in ALLOWED_CHANNEL_IDS:
            channels = " ".join(f"<#{cid}>" for cid in ALLOWED_CHANNEL_IDS)
            await ctx.send(
                embed=yellow_embed(
                    f"⚠️ `$breakdown` can only be used in: {channels}"
                )
            )
            return

        if sentence is None:
            ref = ctx.message.reference
            if ref and ref.message_id:
                try:
                    replied = await ctx.channel.fetch_message(ref.message_id)
                    sentence = replied.content
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

        if not sentence:
            await ctx.send(
                embed=red_embed(
                    "Please provide a sentence or reply to a message.\n"
                    "Usage: `$breakdown <sentence>` or reply with `$breakdown`"
                )
            )
            return

        if len(sentence) < MIN_INPUT_LENGTH:
            await ctx.send(
                embed=red_embed("Please provide a full sentence to break down.")
            )
            return

        if len(sentence) > MAX_INPUT_LENGTH:
            await ctx.send(
                embed=red_embed(
                    f"Sentence is too long ({len(sentence)} chars). "
                    f"Max is {MAX_INPUT_LENGTH} characters."
                )
            )
            return

        detected_lang = detect_message_language(sentence, min_length=MIN_INPUT_LENGTH)
        if detected_lang is None:
            await ctx.send(
                embed=red_embed(
                    "Couldn't detect the language. Please write a clear "
                    "sentence in Spanish or English."
                )
            )
            return

        inp = BreakdownInput(sentence=sentence, detected_language=detected_lang)

        gemini = self.bot.gemini
        if gemini is None:
            await ctx.send(embed=red_embed("Sentence analysis is unavailable right now."))
            return
        processing = await ctx.send("🔍 Analyzing sentence...")

        try:
            result = await gemini.run(BREAKDOWN_PROMPT, inp)
        except GeminiError as e:
            logger.warning("Breakdown Gemini error code=%s: %s", e.code, e.message)
            await processing.edit(content=None, embed=red_embed(e.user_message))
            return
        except ValidationError as e:
            logger.warning("Breakdown parse error: %s", e)
            await processing.edit(
                content=None,
                embed=red_embed(
                    "The sentence was too complex to analyze fully. Try a shorter sentence."
                ),
            )
            return
        except Exception:
            logger.error("Breakdown unexpected error", exc_info=True)
            await processing.edit(
                content=None,
                embed=red_embed("Something went wrong. Please try again later."),
            )
            return

        rendered = render_breakdown(result, detected_lang, detailed=detailed)

        lang_label = "🇪🇸 Spanish" if detected_lang == "es" else "🇺🇸 English"
        embed = discord.Embed(
            title="📝 Sentence Breakdown",
            description=rendered[:4096],
            color=0x5865F2,
        )
        embed.set_footer(text=f"Detected: {lang_label}")

        await processing.edit(content=None, embed=embed)


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    if bot.gemini is None:
        logger.info("bot.gemini is None — BreakdownCog will not load")
        return
    await bot.add_cog(BreakdownCog(bot))
    logger.info("BreakdownCog loaded successfully")
