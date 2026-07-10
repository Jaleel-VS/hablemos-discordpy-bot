"""Breakdown cog — grammatical sentence analysis via Gemini.

Users submit a sentence in Spanish or English with ``$breakdown``, and the
bot responds with a clause-level + word-level grammatical breakdown in the
*other* language (mirror approach).
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.league_cog.utils import detect_message_language
from cogs.utils.embeds import red_embed, yellow_embed
from cogs.utils.gemini import GeminiError

from .config import (
    ALLOWED_CHANNEL_ID,
    COOLDOWN_SECONDS,
    MAX_INPUT_LENGTH,
    MIN_INPUT_LENGTH,
)
from .prompts import BREAKDOWN_PROMPT, BreakdownInput, SentenceBreakdown

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT = 45


def render_breakdown(data: SentenceBreakdown, detected_lang: str) -> str:
    """Render a SentenceBreakdown into markdown for an embed description."""
    lines: list[str] = []

    # Spelling correction
    if data.correction:
        lines.append(f"✏️ **Corrected:** {data.correction}\n")

    # Clause-level + word-level
    for i, clause in enumerate(data.clauses, 1):
        lines.append(f"**Clause {i} — {clause.clause_type}:** *{clause.clause_text}*\n")
        for w in clause.words:
            lines.append(f"• `{w.word}` — {w.part_of_speech} ({w.grammatical_role})")
            lines.append(f"  → {w.translation}")
            if w.notes:
                lines.append(f"  _{w.notes}_")
        lines.append("")

    # Full translation
    lang_arrow = "🇪🇸→🇺🇸" if detected_lang == "es" else "🇺🇸→🇪🇸"
    lines.append(f"**{lang_arrow}** {data.full_translation}")

    return "\n".join(lines)


class BreakdownCog(BaseCog):
    """Sentence breakdown — grammatical analysis powered by Gemini."""

    @commands.command(name="breakdown")
    @commands.cooldown(1, COOLDOWN_SECONDS, commands.BucketType.user)
    async def breakdown(self, ctx: commands.Context, *, sentence: str | None = None):
        """Break down a sentence into its grammatical components.

        Usage:
            $breakdown <sentence in Spanish or English>
            Reply to a message with $breakdown
        """
        # Channel restriction
        if ctx.channel.id != ALLOWED_CHANNEL_ID:
            await ctx.send(
                embed=yellow_embed(
                    f"⚠️ `$breakdown` can only be used in <#{ALLOWED_CHANNEL_ID}>."
                )
            )
            return

        # Resolve sentence from reply if not provided inline
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

        # Validate length
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

        # Detect language
        detected_lang = detect_message_language(sentence)
        if detected_lang is None:
            await ctx.send(
                embed=red_embed(
                    "Couldn't detect the language. Please write a clear "
                    "sentence in Spanish or English."
                )
            )
            return

        # Build input and call Gemini
        inp = BreakdownInput(sentence=sentence, detected_language=detected_lang)

        assert self.bot.gemini is not None  # guarded in setup()
        processing = await ctx.send("🔍 Analyzing sentence...")

        try:
            result = await asyncio.wait_for(
                self.bot.gemini.run(BREAKDOWN_PROMPT, inp),
                timeout=GEMINI_TIMEOUT,
            )
        except TimeoutError:
            await processing.edit(
                content=None,
                embed=red_embed(
                    "Gemini took too long to respond. Please try again."
                ),
            )
            return
        except GeminiError as e:
            logger.warning("Breakdown Gemini error code=%s: %s", e.code, e.message)
            await processing.edit(content=None, embed=red_embed(e.user_message))
            return
        except Exception:
            logger.error("Breakdown unexpected error", exc_info=True)
            await processing.edit(
                content=None,
                embed=red_embed("Something went wrong. Please try again later."),
            )
            return

        # Render structured data into markdown
        rendered = render_breakdown(result, detected_lang)

        # Build response embed
        lang_label = "🇪🇸 Spanish" if detected_lang == "es" else "🇺🇸 English"
        embed = discord.Embed(
            title="📝 Sentence Breakdown",
            description=rendered[:4096],
            color=0x5865F2,
        )
        embed.set_footer(text=f"Detected: {lang_label} • AI-generated analysis")

        await processing.edit(content=None, embed=embed)


async def setup(bot: Hablemos):
    """Required setup fn for loading the cog."""
    if bot.gemini is None:
        logger.info("bot.gemini is None — BreakdownCog will not load")
        return
    await bot.add_cog(BreakdownCog(bot))
    logger.info("BreakdownCog loaded successfully")
